# app/agent/travel/hotel.py
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client
from app.agent.travel.attraction import _run_react_loop, _parse_json_list

_PROMPT = {
    "zh": dedent("""
        你是酒店推荐专家。为以下旅行安排合适的住宿。

        目的地：{destination}
        入住：{check_in}，退房：{check_out}（{days}晚）
        人均预算（住宿）：{hotel_budget:.0f}元/晚
        主要活动区域：{areas}

        使用 ctrip_hotel_search 搜索酒店，用 ctrip_hotel_detail 获取详情。
        推荐 3 个不同价位的酒店选项。

        以 JSON 数组格式输出，每项包含：name、stars、rating、price_per_night、address、amenities、reason、lng（经度，浮点数）、lat（纬度，浮点数）。坐标从携程酒店详情中提取，若无则省略。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a hotel expert. Find suitable accommodations for this trip.

        Destination: {destination}
        Check-in: {check_in}, Check-out: {check_out} ({days} nights)
        Hotel budget: {hotel_budget:.0f} CNY/night
        Activity areas: {areas}

        Use ctrip_hotel_search and ctrip_hotel_detail. Recommend 3 options at different price points.

        Output as JSON array: name, stars, rating, price_per_night, address, amenities, reason, lng (longitude float), lat (latitude float). Extract from ctrip hotel detail; omit if unavailable.
        JSON only.
    """).strip(),
}


async def hotel_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== HotelAgent：推荐酒店 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    budget = trip.budget if trip else 3000.0
    start_date = trip.start_date if trip else ""
    hotel_budget = (budget * 0.4) / days

    attractions = state.get("attractions", [])
    areas = ", ".join(
        {a.get("address", "").split("区")[0] + "区" for a in attractions[:3]
         if "区" in a.get("address", "")}
    ) or destination

    try:
        mcp_client = await get_travel_mcp_client(["ctrip"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, base_url=config.dashscope_api_base, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination,
            check_in=start_date or ("待定" if lang == "zh" else "TBD"),
            check_out=("待定" if lang == "zh" else "TBD"),
            days=days,
            hotel_budget=hotel_budget,
            areas=areas,
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        hotels = _parse_json_list(final_text)
        logger.info(f"HotelAgent 完成，推荐 {len(hotels)} 个酒店")
        return {"hotels": hotels}

    except Exception as e:
        logger.exception("HotelAgent 失败: {}", repr(e))
        return {"hotels": [], "errors": {"hotel": str(e)}}
