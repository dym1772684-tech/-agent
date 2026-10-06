from pydantic import BaseModel,Field
from typing import Callable
from langchain.tools import tool,ToolRuntime
from langchain.messages import ToolMessage
import requests
import os
from langgraph.types import Command
from allagent.guance.logging_helper import logger
from allagent.agent.state import state_schema
class defInfo(BaseModel):#函数的参数
    number1:float
    number2:float
    fuhao:str
@tool("calculator",description="计算",args_schema=defInfo)
def jisuan(fuhao,number1,number2):
    logger.info("调用 calculator，参数 fuhao=%s, number1=%s, number2=%s", fuhao, number1, number2)
    try:
        fuhao_map = {"加法":"+", "减法":"-","乘法":"*","除法":"/"}
        fuhao = fuhao_map.get(fuhao, fuhao)
        number1 = float(number1)
        number2 = float(number2)
        if fuhao=="+":
            result = str(number1+number2)
        elif fuhao=="-":
            result = str(number1-number2)
        elif fuhao=="*":
            result = str(number1*number2)
        elif fuhao=="/":
            if number2==0:
                result = "除数不能为0"
            else:
                result = str(number1/number2)
        else:
            result = "错误输入"
        logger.info("calculator 返回 %s", result)
        return result
    except Exception as exc:
        logger.exception("calculator 计算失败")
        return "计算失败"



class location(BaseModel):
    city_name:str=Field(description="City name or coordinates")
@tool("get_real_weather",description="用来获得天气",args_schema=location,return_direct=False)
#这个args_schema 可以使用json（也就是之前的sdk，然后的话也可以使用pydantic
def get_real_weather(city_name:str,runtime:ToolRuntime=None):
    logger.info("调用 get_real_weather，city_name=%s", city_name)
    try:
        geo_param = {
            "q": city_name,
            "appid": os.getenv("WEATHER_API_KEY"),
            "limit": 1,"lang": "zh_cn"
        }
        geo_response = requests.get("http://api.openweathermap.org/geo/1.0/direct", params=geo_param)
        geo_response.raise_for_status()
        geo_data = geo_response.json()
        lon = geo_data[0]["lon"]
        lat = geo_data[0]["lat"]

        weather_param = {
            "lat": lat,
            "lon": lon,
            "appid": os.getenv("WEATHER_API_KEY"),
            "lang": "zh_cn","units": "metric"
        }
        weather_response = requests.get("https://api.openweathermap.org/data/2.5/weather", params=weather_param)
        weather_response.raise_for_status()
        weather_data = weather_response.json()

        desc = weather_data["weather"][0]["description"]
        temp = weather_data["main"]["temp"]
        city = weather_data["name"]
        result = f"{city}:{desc}，当前温度{temp}℃"
        logger.info("get_real_weather 返回 %s", result)
        return result
    except Exception as e:
        logger.exception("get_real_weather 失败")
        return f"获取天气失败：{str(e)}"

#    @dataclass
# class ToolRuntime[ContextT]:
#     state: dict                  # 当前Agent全局状态（可变）
#     context: ContextT | dict    # 会话固定配置（不可变）
#     store: BaseStore | None     # 跨对话长期持久记忆
#     stream_writer: StreamWriter # 实时流式输出
#     previous: Any               # 上一轮节点返回结果
#     tool_call_id: str           # 当前本次工具调用唯一ID
tools=[jisuan,get_real_weather]
tools_name={tool.name:tool for tool in tools}
class CustomState(state_schema):
    user_name: str

class CustomContext(BaseModel):
    user_id: str

@tool
def update_user_info(
    runtime: ToolRuntime[CustomContext, CustomState],
) -> Command:
    """Look up and update user info."""
    user_id = runtime.context.user_id
    name = "John Smith" if user_id == "user_123" else "Unknown user"
    return Command(update={
        "user_name": name,
        # update the message history
        "messages": [
            ToolMessage(
                "Successfully looked up user information",
                tool_call_id=runtime.tool_call_id
            )
        ]
    })