# app/agent/travel/food.py
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
        你是{destination}本地美食专家。推荐当地最值得去的餐厅，供游客自由选择。

        偏好：{preferences}
        人均餐饮预算参考：{food_budget:.0f}元/餐
        活动区域：{areas}

        使用 dianping_restaurant_search 搜索餐厅，用 dianping_menu 查看招牌菜。
        推荐 10-15 家不同菜系、不同价位的特色餐厅，覆盖景区周边及当地网红店。

        以 JSON 数组格式输出，每项包含：
        name、cuisine（菜系）、avg_price_per_person（人均价格，整数）、address、
        signature_dishes（招牌菜列表）、reason（推荐理由，一句话）、
        lng（经度，浮点数）、lat（纬度，浮点数）。
        坐标从搜索结果中提取，若无则省略这两个字段。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a local food expert in {destination}. Recommend the best restaurants for tourists to freely choose from.

        Preferences: {preferences}
        Budget reference: {food_budget:.0f} CNY/meal/person
        Activity areas: {areas}

        Use dianping_restaurant_search and dianping_menu. Recommend 10-15 restaurants of varied cuisines and price ranges.

        Output as JSON array: name, cuisine, avg_price_per_person (integer), address,
        signature_dishes (list), reason (one sentence), lng (float), lat (float).
        Extract coordinates from search results; omit if unavailable.
        JSON only.
    """).strip(),
}


async def food_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== FoodAgent：推荐美食 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    budget = trip.budget if trip else 3000.0
    food_budget = (budget * 0.3) / days
    preferences = (", ".join(trip.preferences) if trip and trip.preferences
                   else ("无特定偏好" if lang == "zh" else "none"))

    attractions = state.get("attractions", [])
    areas = ", ".join(
        {a.get("address", "").split("区")[0] + "区" for a in attractions[:3]
         if "区" in a.get("address", "")}
    ) or destination

    try:
        mcp_client = await get_travel_mcp_client(["dianping"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, base_url=config.dashscope_api_base, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination, preferences=preferences,
            food_budget=food_budget, areas=areas,
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        foods = _parse_json_list(final_text)
        from app.agent.travel.geo_utils import fill_coordinates
        foods = await fill_coordinates(foods, destination, config.gaode_api_key)
        logger.info(f"FoodAgent 完成，推荐 {len(foods)} 个餐厅（含坐标补全）")
        return {"foods": foods}

    except Exception as e:
        logger.exception("FoodAgent 失败: {}", repr(e))
        return {"foods": [], "errors": {"food": str(e)}}
