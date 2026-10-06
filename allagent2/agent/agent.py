from __future__ import annotations

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.messages import BaseMessage

from allagent.agent.state import ParsedOutput
from allagent.guance.logging_helper import logger
from allagent.tools.tool import tools

BASE_DIR = Path(__file__).resolve().parent.parent
ENV_PATH = BASE_DIR / "core" / "key.env"
load_dotenv(find_dotenv(str(ENV_PATH)))


class _FallbackModel:
    """当 LLM / SDK / API 不可用时，返回安全空结构，保证服务能启动和接口返回。"""

    def __init__(self, *, fallback_content: str = ""):
        self.fallback_content = fallback_content

    def invoke(self, messages, *args, **kwargs):
        last = messages[-1].content if messages else self.fallback_content
        return {"content": last, "parsed": {}}

    def bind_tools(self, tools_list):
        return self

    def with_structured_output(self, schema, include_raw=True):
        return self


def create_parser_model(api_key: str, base_url: str):
    logger.info("创建 parser model，api_key present=%s, base_url=%s", api_key is not None, base_url)
    try:
        model = init_chat_model(
            model="deepseek-chat",
            api_key=api_key,
            base_url=base_url,
            temperature=1,
            max_tokens=1024,
            timeout=30,
            max_retries=3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        model = model.with_structured_output(ParsedOutput, include_raw=True)
        logger.info("parser model 创建完成")
        return model
    except Exception as exc:
        logger.warning("parser model 创建失败，使用兜底模型：%s", exc)
        return _FallbackModel(fallback_content="parser fallback")


def create_tool_model(api_key: str, base_url: str):
    logger.info("创建 tool model，api_key present=%s, base_url=%s", api_key is not None, base_url)
    try:
        model = init_chat_model(
            model="deepseek-chat",
            api_key=api_key,
            base_url=base_url,
            temperature=1,
            max_tokens=1024,
            timeout=30,
            max_retries=3,
            extra_body={"thinking": {"type": "disabled"}},
        )
        model = model.bind_tools(tools)
        logger.info("tool model 创建完成")
        return model
    except Exception as exc:
        logger.warning("tool model 创建失败，使用兜底模型：%s", exc)
        return _FallbackModel(fallback_content="tool fallback")


def agent_invoke(model, state):
    logger.info("agent_invoke 开始，消息数量=%d", len(state.get("messages", [])))
    try:
        result = model.invoke(state["messages"])
        logger.info(
            "agent_invoke 完成，type=%s, content=%s, tool_calls=%s",
            type(result),
            getattr(result, "content", None),
            getattr(result, "tool_calls", None),
        )
        return result
    except Exception:
        logger.exception("agent_invoke 失败")
        raise
