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
        你是美食推荐专家。为{destination}的旅行安排美食计划。

        偏好：{preferences}
        人均餐饮预算：{food_budget:.0f}元/天
        活动区域：{areas}

        使用 dianping_restaurant_search 搜索餐厅，用 dianping_menu 查看招牌菜。
        按早/午/晚餐推荐，覆盖不同菜系和价位。

        以 JSON 数组格式输出，每项包含：name、cuisine、avg_price_per_person、address、signature_dishes、meal_type（breakfast/lunch/dinner）、reason。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a food expert. Plan dining for a trip to {destination}.

        Preferences: {preferences}
        Daily food budget: {food_budget:.0f} CNY/person
        Activity areas: {areas}

        Use dianping_restaurant_search and dianping_menu. Cover breakfast, lunch, and dinner.

        Output as JSON array: name, cuisine, avg_price_per_person, address, signature_dishes, meal_type, reason.
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
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination, preferences=preferences,
            food_budget=food_budget, areas=areas,
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        foods = _parse_json_list(final_text)
        logger.info(f"FoodAgent 完成，推荐 {len(foods)} 个餐厅")
        return {"foods": foods}

    except Exception as e:
        logger.error(f"FoodAgent 失败: {e}", exc_info=True)
        return {"foods": [], "errors": {"food": str(e)}}
