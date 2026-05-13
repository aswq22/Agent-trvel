# app/agent/travel/route.py
import json
import re
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, BaseMessage
from loguru import logger

from app.core.llm_factory import LLMFactory
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client
from app.agent.travel.attraction import _run_react_loop

_PROMPT = {
    "zh": dedent("""
        你是路线规划专家。根据以下景点，规划{days}天的最优游览路线。

        目的地：{destination}
        天数：{days}天
        景点列表：
        {attractions_text}

        使用 gaode_distance_matrix 计算景点间距离，用 gaode_route_plan 获取路线详情。
        规划原则：
        - 地理位置相近的景点安排在同一天
        - 考虑景点开放时间和参观时长
        - 每天不超过 3 个主要景点

        以 JSON 格式输出，结构：
        {{
          "days": [
            {{"day": 1, "theme": "主题", "attractions": ["景点A", "景点B"], "transport": "交通方式", "tips": "当日提示"}},
            ...
          ],
          "total_distance_km": 数字
        }}
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a route planning expert. Plan the optimal {days}-day route for these attractions.

        Destination: {destination}
        Duration: {days} days
        Attractions:
        {attractions_text}

        Use gaode_distance_matrix for distances, gaode_route_plan for route details.
        Output as JSON:
        {{
          "days": [
            {{"day": 1, "theme": "theme", "attractions": ["A", "B"], "transport": "transport", "tips": "tip"}},
            ...
          ],
          "total_distance_km": number
        }}
        JSON only, no extra text.
    """).strip(),
}


def _parse_json_dict(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"raw": text}


async def route_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== RouteAgent：规划路线 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    attractions = state.get("attractions", [])

    attractions_text = "\n".join(
        f"- {a.get('name', 'Unknown')} ({a.get('address', '')})"
        for a in attractions
    ) or ("暂无景点数据" if lang == "zh" else "No attractions data")

    try:
        mcp_client = await get_travel_mcp_client(["gaode"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = LLMFactory.create_travel_llm(temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination, days=days, attractions_text=attractions_text
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        route = _parse_json_dict(final_text)
        logger.info(f"RouteAgent 完成，规划 {len(route.get('days', []))} 天行程")
        return {"route": route}

    except Exception as e:
        logger.exception("RouteAgent 失败: {}", repr(e))
        return {"route": {}, "errors": {"route": str(e)}}
