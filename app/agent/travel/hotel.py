# app/agent/travel/hotel.py
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, BaseMessage
from loguru import logger

from app.config import config
from app.core.llm_factory import LLMFactory
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

_FALLBACK_PROMPT = {
    "zh": dedent("""
        你是酒店推荐专家，请根据自己的知识为以下旅行推荐 3 个真实存在的酒店（不同价位）。

        目的地：{destination}
        天数：{days}晚
        人均住宿预算：{hotel_budget:.0f}元/晚
        主要活动区域：{areas}

        请推荐真实的、知名的酒店，包含具体地址和价格估算。

        只输出 JSON 数组，每项包含：
        - name（酒店名称）
        - stars（星级，整数 3-5）
        - rating（评分，浮点数 4.0-5.0）
        - price_per_night（每晚价格，整数）
        - address（详细地址）
        - amenities（设施列表，数组）
        - reason（推荐理由）
        - lng（经度，浮点数，必填）
        - lat（纬度，浮点数，必填）

        不要输出任何说明文字，只输出 JSON。
    """).strip(),
    "en": dedent("""
        You are a hotel expert. Based on your knowledge, recommend 3 real hotels at different price points.

        Destination: {destination}
        Duration: {days} nights
        Hotel budget: {hotel_budget:.0f} CNY/night
        Activity areas: {areas}

        Recommend real, well-known hotels with specific addresses and estimated prices.

        Output JSON array only, each item: name, stars (3-5), rating (4.0-5.0), price_per_night (int),
        address, amenities (array), reason, lng (float, required), lat (float, required).
        No explanations, JSON only.
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

    fmt = dict(
        destination=destination,
        check_in=start_date or ("待定" if lang == "zh" else "TBD"),
        check_out=("待定" if lang == "zh" else "TBD"),
        days=days,
        hotel_budget=hotel_budget,
        areas=areas,
    )

    hotels: List[dict] = []

    def _valid(h_list: List[dict]) -> bool:
        """真正有内容的酒店列表（至少有一个 dict 且有 name 字段）"""
        return any(isinstance(h, dict) and h.get("name") for h in h_list)

    # --- 尝试 MCP 工具搜索 ---
    try:
        mcp_client = await get_travel_mcp_client(["ctrip"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = LLMFactory.create_travel_llm(temperature=0, disable_thinking=True)
        llm_with_tools = llm.bind_tools(tools) if tools else llm
        messages: List[BaseMessage] = [HumanMessage(content=_PROMPT[lang].format(**fmt))]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        hotels = _parse_json_list(final_text)
        logger.info(f"HotelAgent MCP 结果: {len(hotels)} 个酒店，有效: {_valid(hotels)}")
    except Exception as e:
        logger.warning("HotelAgent MCP 失败，将使用 LLM 自有知识兜底: {}", repr(e))

    # --- MCP 无有效结果时用 LLM 自有知识兜底 ---
    if not _valid(hotels):
        try:
            logger.info("HotelAgent 兜底：使用 DeepSeek 自有知识推荐酒店")
            llm = LLMFactory.create_travel_llm(temperature=0.3, disable_thinking=True)
            response = await llm.ainvoke([HumanMessage(content=_FALLBACK_PROMPT[lang].format(**fmt))])
            content = response.content if hasattr(response, "content") else str(response)
            hotels = _parse_json_list(content)
            logger.info(f"HotelAgent 兜底完成，推荐 {len(hotels)} 个酒店，有效: {_valid(hotels)}")
        except Exception as e:
            logger.exception("HotelAgent 兜底也失败: {}", repr(e))
            return {"hotels": [], "errors": {"hotel": str(e)}}

    try:
        from app.agent.travel.geo_utils import fill_coordinates
        hotels = await fill_coordinates(hotels, destination, config.gaode_api_key)
    except Exception:
        pass

    logger.info(f"HotelAgent 完成，共 {len(hotels)} 个酒店（含坐标补全）")
    return {"hotels": hotels}
