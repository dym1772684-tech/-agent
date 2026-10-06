"""Agent 数据访问与敏感信息中间件（middleware 层）。

【安全模型】
1. DBAccessMiddleware —— 唯一允许访问数据库的组件（DB 网关）。
   - 智能体（LangGraph）的工具调用一律经过本网关：鉴权 → 查询 → 敏感扫描 → JSON 返回；
   - 数据库工具函数本身不再持有任何 DB engine/连接（见 backend_tools.py 的薄壳改造），
     真正执行查询的代码只存在于本网关内部 → “智能体不能自己调用数据库，只让 middleware 调”。
   - 每次 DB 调用都做鉴权（工具白名单 / 老人数据越权 / 角色），默认“拒绝”兜底（fail closed）。

2. SensitiveGuard —— 入口级敏感阻断。
   - 在智能体链路启动前（LLM 进入之前）扫描用户消息，命中敏感信息请求且无权限
     → 直接阻断，不进入智能体链路。

3. 鉴权上下文通过线程局部变量（thread-local）传递：
   - run_agent / HTTP router 入口调用 set_access_context() 注入当前用户权限；
   - 网关执行时读取；无上下文 = 按 common + 不允许敏感处理（安全默认）。

返回给智能体服务层的标准 JSON 格式：
   正常  ： {"code": 0,   "data": {"tool": "<工具名>", "result": "<查询结果>"}}
   无权限： {"code": 403, "msg": "<拒绝原因>"}
   敏感阻断：{"code": 451, "msg": "<阻断原因>"}
"""
from __future__ import annotations

import json
import os
import re
import threading
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import create_engine, desc, select
from sqlalchemy.orm import Session

from models.elder import Elder
from models.health import HealthRecord


# ============================================================
# 1. 线程局部鉴权上下文
# ============================================================
class _AccessContext:
    __slots__ = ("permissions", "user_role", "allow_sensitive", "authenticated")

    def __init__(
        self,
        permissions: Optional[dict] = None,
        user_role: str = "common",
        allow_sensitive: bool = False,
        authenticated: bool = True,
    ) -> None:
        self.permissions: Dict[str, Any] = permissions or {}
        self.user_role: str = user_role or "common"
        self.allow_sensitive: bool = bool(allow_sensitive)
        # 【安全】authenticated=False 表示"没有注入鉴权上下文"（未登录/非正规入口），
        # 网关对这类调用一律拒绝数据库访问（fail closed）
        self.authenticated: bool = authenticated


_ACCESS_CTX = threading.local()


def set_access_context(
    permissions: Optional[dict] = None,
    user_role: str = "common",
    allow_sensitive: bool = False,
) -> None:
    """【鉴权】入口注入当前用户的权限上下文（每次请求/调用开始时设置）。"""
    _ACCESS_CTX.ctx = _AccessContext(permissions, user_role, allow_sensitive)


def clear_access_context() -> None:
    """【鉴权】请求结束后清理，防止线程复用导致权限串号。"""
    _ACCESS_CTX.ctx = None


def get_access_context() -> _AccessContext:
    """【鉴权】读取当前线程的权限上下文；无上下文 = 未登录，按 fail closed 拒绝。"""
    ctx = getattr(_ACCESS_CTX, "ctx", None)
    if ctx is None:
        return _AccessContext(None, "common", False, authenticated=False)
    return ctx


# ============================================================
# 2. 敏感信息规则（PII 正则 / 字段名 / 意图词）
# ============================================================
# PII 正则：命中即脱敏（无权限时）
PII_PATTERNS: List[Tuple[re.Pattern, str]] = [
    (re.compile(r"\b\d{17}[\dXx]\b"), "身份证号"),
    (re.compile(r"\b1[3-9]\d{9}\b"), "手机号"),
    (re.compile(r"\b0\d{2,3}-?\d{7,8}\b"), "座机电话"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+"), "邮箱"),
]

# 强敏感字段名：结果中出现这些 → 无权限时整条数据阻断（不给 model 原文）
STRONG_SENSITIVE_FIELDS = ("身份证", "id_card", "完整病史", "病历", "医保")

# 一般敏感字段名：无权限时脱敏处理（弱敏感）
WEAK_SENSITIVE_FIELDS = ("联系电话", "phone", "家庭住址", "住址", "address", "手机号")

# 意图级敏感词：用户消息请求这些内容 → 入口阻断
SENSITIVE_INTENT_KEYWORDS = (
    "身份证",
    "手机号",
    "联系电话",
    "家庭住址",
    "住址",
    "医保",
    "完整病史",
    "病历明细",
    "隐私",
)


def _mask_pii(text: str) -> str:
    """对文本中的 PII 做脱敏（保持格式可读但不泄露原文）。"""
    def mask_phone(m: re.Match) -> str:
        s = m.group(0)
        return s[:3] + "****" + s[7:] if len(s) >= 11 else s[:3] + "****"

    def mask_idcard(m: re.Match) -> str:
        s = m.group(0)
        return s[:6] + "********" + s[-4:] if len(s) >= 15 else "********"

    def mask_landline(m: re.Match) -> str:
        s = m.group(0)
        return s[:3] + "****" + s[-2:]

    def mask_email(m: re.Match) -> str:
        s = m.group(0)
        at = s.find("@")
        return s[:3] + "***" + s[at:] if at > 3 else "***" + s[at:]

    text = PII_PATTERNS[0][0].sub(mask_idcard, text)
    text = PII_PATTERNS[1][0].sub(mask_phone, text)
    text = PII_PATTERNS[2][0].sub(mask_landline, text)
    text = PII_PATTERNS[3][0].sub(mask_email, text)
    return text


# ============================================================
# 3. DBAccessMiddleware —— 唯一允许访问数据库的组件
# ============================================================
class DBAccessMiddleware:
    """数据库访问网关（单例）。

    智能体每次调用数据库工具，最终都会执行到这里：
    authorize（鉴权）→ _query_*（只有这里查库）→ 敏感扫描 → JSON 返回。
    """

    _instance: "DBAccessMiddleware | None" = None
    _engine: Any = None
    _engine_lock = threading.Lock()

    DB_TOOLS = ("query_elder_profile", "query_health_records")

    @classmethod
    def get(cls) -> "DBAccessMiddleware":
        if cls._instance is None:
            cls._instance = DBAccessMiddleware()
        return cls._instance

    # ---- 统一入口：每次 DB 调用都经过这里 ----
    def execute(self, tool_name: str, args: dict) -> str:
        """【鉴权】网关统一执行入口，返回 JSON 字符串（智能体服务层标准格式）。"""
        ctx = get_access_context()

        # 1) 鉴权（每次调用都执行；无权限直接拒绝，不触碰数据库）
        err = self._authorize(tool_name, args, ctx)
        if err:
            return json.dumps({"code": 403, "msg": err}, ensure_ascii=False)

        # 2) 查询（只有网关内部持有 DB engine）
        try:
            if tool_name == "query_elder_profile":
                raw = self._query_profile(args.get("elder_id"))
            elif tool_name == "query_health_records":
                raw = self._query_health(args.get("elder_id"), args.get("metric_type"))
            else:
                return json.dumps(
                    {"code": 400, "msg": f"网关不支持的数据库工具: {tool_name}"},
                    ensure_ascii=False,
                )
        except Exception as exc:  # 异常不外泄细节给 model
            return json.dumps(
                {"code": 500, "msg": "数据库查询失败（详情已脱敏，请联系管理员查看日志）"},
                ensure_ascii=False,
            )

        # 3) 敏感扫描：强敏感且无权限 → 阻断；否则脱敏
        blocked, safe_text = self._scan_sensitive(raw, ctx)
        if blocked:
            return json.dumps(
                {"code": 451, "msg": "检测到敏感信息（身份证/完整病史等），已阻断，不进入智能体链路"},
                ensure_ascii=False,
            )

        # 4) JSON 化返回给智能体服务层
        return json.dumps(
            {"code": 0, "data": {"tool": tool_name, "result": safe_text}},
            ensure_ascii=False,
        )

    # ---- 鉴权 ----
    def _authorize(self, tool_name: str, args: dict, ctx: _AccessContext) -> Optional[str]:
        """鉴权失败返回错误文案；通过返回 None。"""
        # 【安全】未注入鉴权上下文（未登录/非正规入口）→ 一律拒绝数据库访问
        if not ctx.authenticated:
            return "未注入鉴权上下文，拒绝访问数据库（请先登录）"

        # 工具白名单（默认四工具；外部可注入 allowed_tools 收紧）
        allowed_tools = ctx.permissions.get("allowed_tools")
        if allowed_tools is not None and tool_name not in allowed_tools:
            return f"无权调用工具 {tool_name}（不在白名单内）"

        # 老人数据类工具：必须有 elder_id，且不得越权访问其他老人
        if tool_name in ("query_elder_profile", "query_health_records"):
            elder_id = (args or {}).get("elder_id")
            if not elder_id:
                return "缺少老人编号 elder_id，无法查询"
            allowed_ids = ctx.permissions.get("allowed_elder_ids")
            if allowed_ids is not None and elder_id not in allowed_ids:
                return f"无权访问老人 {elder_id} 的数据（超出授权范围）"
        return None

    # ---- 查询（仅网关内部调用；DB 逻辑从 backend_tools 迁移至此） ----
    def _get_engine(self) -> Any:
        if DBAccessMiddleware._engine is None:
            with DBAccessMiddleware._engine_lock:  # 双检锁，单例连接池
                if DBAccessMiddleware._engine is None:
                    user = os.getenv("MYSQL_USER", "root")
                    pwd = os.getenv("MYSQL_PASSWORD", "")
                    host = os.getenv("MYSQL_HOST", "127.0.0.1")
                    port = os.getenv("MYSQL_PORT", "3306")
                    db = os.getenv("MYSQL_DATABASE", "")
                    url = f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}?charset=utf8mb4"
                    DBAccessMiddleware._engine = create_engine(url, pool_pre_ping=True)
        return DBAccessMiddleware._engine

    def _query_profile(self, elder_id: Optional[str]) -> str:
        with Session(self._get_engine()) as session:
            elder = session.execute(
                select(Elder).where(Elder.elder_id == elder_id)
            ).scalar_one_or_none()
            if elder is None:
                return "档案里没有该老人的记录"
            return (
                f"姓名：{elder.name}；年龄：{elder.age}；性别：{elder.gender}；"
                f"自理状态：{elder.health_tag}；慢性病：{elder.chronic_disease}；联系电话：{elder.phone}"
            )

    @staticmethod
    def _format_record(r) -> str:
        # 【健壮性】部分历史数据可能没有 record_time，显式兜底为“时间未知”
        t = r.record_time if r.record_time is not None else "时间未知"
        return f"{t} {r.metric_type}={r.value}"

    def _query_health(self, elder_id: Optional[str], metric_type: Optional[str] = None) -> str:
        with Session(self._get_engine()) as session:
            stmt = select(HealthRecord).where(HealthRecord.elder_id == elder_id)
            if metric_type:
                stmt = stmt.where(HealthRecord.metric_type == metric_type)
            stmt = stmt.order_by(desc(HealthRecord.record_time)).limit(10)
            rows = session.execute(stmt).scalars().all()
            if not rows:
                return "档案里没有该老人的健康监测记录"
            return "；".join(self._format_record(r) for r in rows)

    # ---- 敏感扫描 ----
    def _scan_sensitive(self, text: str, ctx: _AccessContext) -> Tuple[bool, str]:
        """返回 (是否阻断, 处理后的文本)。无权限时强敏感字段 → 阻断，其余脱敏。"""
        if not text:
            return False, text
        # 强敏感字段名命中且无权限 → 阻断（不给 model 原文）
        if not ctx.allow_sensitive:
            for f in STRONG_SENSITIVE_FIELDS:
                if f in text:
                    return True, text
        # 弱敏感：无权限 → 脱敏；有权限 → 原样返回
        if ctx.allow_sensitive:
            return False, text
        masked = _mask_pii(text)
        return False, masked


# ============================================================
# 4. SensitiveGuard —— 入口级敏感阻断（LLM 链路之前）
# ============================================================
class SensitiveGuard:
    """入口守卫：智能体链路启动前阻断敏感请求，避免 model 识别到敏感信息。"""

    @staticmethod
    def check(message: str, permissions: Optional[dict]) -> Optional[dict]:
        """返回 None = 放行；返回 dict = 阻断响应（不进入智能体链路）。"""
        if not message:
            return None
        allow_sensitive = bool((permissions or {}).get("allow_sensitive"))
        if allow_sensitive:
            return None
        hits = [kw for kw in SENSITIVE_INTENT_KEYWORDS if kw in message]
        if hits:
            return {
                "code": 403,
                "msg": f"检测到敏感信息请求（{', '.join(hits)}），已阻断，不进入智能体链路",
            }
        return None


# ============================================================
# 5. AgentSecurityService —— 安全服务门面（对外唯一调用入口）
# ============================================================
class AgentSecurityService:
    """统一安全服务门面：外部（HTTP 路由 / 智能体服务层）只调用本类的方法，
    所有鉴权 / 敏感阻断 / DB 网关逻辑均收敛在 middleware.py 内部。
    """

    @staticmethod
    def build_permissions(
        current_user: Any,
        allowed_elder_ids: Optional[list] = None,
        allowed_tools: Optional[list] = None,
    ) -> dict:
        """【鉴权】由登录用户 + 请求约束生成权限上下文。

        - admin：allow_sensitive=True（可看敏感字段、可访问全部范围）
        - common：allow_sensitive=False（敏感信息一律脱敏/阻断）
        - allowed_elder_ids / allowed_tools 可进一步收紧范围
        """
        user_role = getattr(current_user, "user_role", "common")
        permissions: dict = {
            "user_role": user_role,
            "allow_sensitive": user_role == "admin",
        }
        if allowed_elder_ids is not None:
            permissions["allowed_elder_ids"] = allowed_elder_ids
        if allowed_tools is not None:
            permissions["allowed_tools"] = allowed_tools
        return permissions

    @staticmethod
    def guard_message(message: str, permissions: dict) -> Optional[dict]:
        """【安全】入口敏感阻断：返回 None=放行；dict=阻断（不进入智能体链路）。"""
        return SensitiveGuard.check(message, permissions)

    @staticmethod
    def enter_context(permissions: dict) -> None:
        """【鉴权】注入线程级鉴权上下文（供 DBAccessMiddleware 每次 DB 调用读取）。"""
        user_role = (permissions or {}).get("user_role") or "common"
        allow_sensitive = bool((permissions or {}).get("allow_sensitive", False))
        set_access_context(permissions, user_role, allow_sensitive)

    @staticmethod
    def exit_context() -> None:
        """【鉴权】清理线程级上下文，防止线程复用导致权限串号。"""
        clear_access_context()

    @staticmethod
    def query_elder_profile_safe(elder_id: str) -> str:
        """【服务】查询老人档案（经网关：鉴权 → 查询 → 敏感扫描 → JSON 返回）。"""
        return DBAccessMiddleware.get().execute("query_elder_profile", {"elder_id": elder_id})

    @staticmethod
    def query_health_records_safe(elder_id: str, metric_type: Optional[str] = None) -> str:
        """【服务】查询老人健康记录（经网关：鉴权 → 查询 → 敏感扫描 → JSON 返回）。"""
        return DBAccessMiddleware.get().execute(
            "query_health_records", {"elder_id": elder_id, "metric_type": metric_type}
        )
