# app/agent/travel/attraction.py
import json
import re
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client

_PROMPT = {
    "zh": dedent("""
        你是景点推荐专家。使用工具搜索{destination}的热门景点。

        旅行信息：
        - 目的地：{destination}
        - 天数：{days}天
        - 偏好：{preferences}

        步骤：
        1. 用 gaode_poi_search 搜索 "{destination} 景点"
        2. 用 dianping_attraction_search 搜索 {destination} 景点
        3. 综合两个来源，推荐最适合 {days} 天行程的 {num} 个景点

        最终以 JSON 数组格式输出景点，每项包含：name、address、rating、ticket_price、highlights、reason、lng（经度，浮点数）、lat（纬度，浮点数）。坐标从高德 POI 搜索结果中提取，若无则省略。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are an attractions expert. Use tools to find top attractions in {destination}.

        Trip info:
        - Destination: {destination}
        - Duration: {days} days
        - Preferences: {preferences}

        Steps:
        1. Use gaode_poi_search to search "{destination} attractions"
        2. Use dianping_attraction_search to search attractions in {destination}
        3. Recommend the best {num} attractions for a {days}-day trip

        Output as a JSON array only. Each item: name, address, rating, ticket_price, highlights, reason, lng (longitude float), lat (latitude float). Extract coordinates from gaode POI results; omit if unavailable.
    """).strip(),
}


async def _run_react_loop(
    messages: List[BaseMessage],
    llm_with_tools,
    tool_map: dict,
    max_turns: int = 5,
) -> str:
    """Generic ReAct loop: LLM → tool calls → LLM → ... → final text."""
    for _ in range(max_turns):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not (hasattr(response, "tool_calls") and response.tool_calls):
            return response.content if hasattr(response, "content") else str(response)

        for tc in response.tool_calls:
            tool = tool_map.get(tc["name"])
            if tool:
                try:
                    result = await tool.ainvoke(tc["args"])
                except Exception as e:
                    result = f"ERROR: {e}"
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"])
                )

    return messages[-1].content if hasattr(messages[-1], "content") else ""


def _parse_json_list(text: str) -> List[dict]:
    match = re.search(r"\[.*\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return [{"raw": text}]


async def attraction_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== AttractionAgent：搜索景点 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    preferences = ", ".join(trip.preferences) if trip and trip.preferences else ("无特定偏好" if lang == "zh" else "none")
    num = days * 5  # 每天安排 4-5 个景点

    try:
        mcp_client = await get_travel_mcp_client(["gaode", "dianping"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, base_url=config.dashscope_api_base, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(destination=destination, days=days, preferences=preferences, num=num)
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        attractions = _parse_json_list(final_text)
        logger.info(f"AttractionAgent 完成，推荐 {len(attractions)} 个景点")
        return {"attractions": attractions}

    except Exception as e:
        logger.exception("AttractionAgent 失败: {}", repr(e))
        return {"attractions": [], "errors": {"attraction": str(e)}}
