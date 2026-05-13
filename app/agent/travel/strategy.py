# app/agent/travel/strategy.py
import json
from textwrap import dedent
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState

_SYSTEM = {
    "zh": dedent("""
        你是资深旅游攻略专家。根据以下信息，生成一份完整的逐日旅游攻略。

        攻略要求：
        - 按天组织，每天包含：上午/下午/晚上的安排
        - 每个景点说明参观时长和注意事项
        - 每顿饭推荐具体餐厅和招牌菜
        - 每晚住宿说明酒店名称和价格
        - 结尾加上交通、天气、行李等实用Tips
        - 格式使用 Markdown，清晰易读

        如果某类信息缺失（标注"暂不可用"），跳过该部分，用通用建议代替。
    """).strip(),
    "en": dedent("""
        You are an expert travel planner. Generate a complete day-by-day travel guide.

        Requirements:
        - Organize by day: morning/afternoon/evening
        - Include duration and tips for each attraction
        - Recommend specific restaurants for each meal
        - Include hotel name and price for each night
        - End with practical tips: transport, weather, packing
        - Use Markdown format

        If any data is marked "unavailable", skip and use general advice instead.
    """).strip(),
}


def _build_context(state: TravelPlanState, lang: str) -> str:
    trip = state["trip_params"]
    errors = state.get("errors", {})

    def safe(data, label):
        if not data:
            return f"{label}: {'暂不可用' if lang == 'zh' else 'unavailable'}\n"
        return f"{label}:\n{json.dumps(data, ensure_ascii=False, indent=2)}\n"

    ctx = ""
    if trip:
        ctx += (f"旅行参数: {trip.model_dump_json(ensure_ascii=False)}\n\n"
                if lang == "zh" else f"Trip params: {trip.model_dump_json()}\n\n")
    ctx += safe(state.get("attractions"), "景点列表" if lang == "zh" else "Attractions")
    ctx += safe(state.get("route"), "路线规划" if lang == "zh" else "Route")
    ctx += safe(state.get("hotels"), "酒店选项" if lang == "zh" else "Hotels")
    ctx += safe(state.get("foods"), "美食推荐" if lang == "zh" else "Food")

    if errors:
        ctx += (f"\n注意，以下数据获取失败（已用内置知识补充）：{list(errors.keys())}\n"
                if lang == "zh"
                else f"\nNote: The following data failed to load (using built-in knowledge): {list(errors.keys())}\n")
    return ctx


def _build_structured_plan(state: TravelPlanState) -> dict:
    """Assemble structured day-by-day plan from state data (no extra LLM call)."""
    trip = state.get("trip_params")
    if not trip:
        return {}

    days_count = trip.days
    attractions = state.get("attractions") or []
    hotels = state.get("hotels") or []
    food_list = state.get("foods") or []
    budget = trip.budget
    start_date = trip.start_date

    per_day_attr = max(1, (len(attractions) + days_count - 1) // days_count)
    per_day_food = max(2, (len(food_list) + days_count - 1) // days_count)

    days = []
    for i in range(1, days_count + 1):
        if start_date:
            try:
                from datetime import datetime, timedelta
                base = datetime.strptime(start_date, "%Y-%m-%d")
                day_date = (base + timedelta(days=i - 1)).strftime("%Y-%m-%d")
            except ValueError:
                day_date = f"第{i}天"
        else:
            day_date = f"第{i}天"

        day_attr_raw = attractions[(i - 1) * per_day_attr: i * per_day_attr]
        day_attractions = []
        for a in day_attr_raw:
            highlights = a.get("highlights", "")
            tip = highlights[0] if isinstance(highlights, list) and highlights else str(highlights)
            entry: dict = {"name": a.get("name", ""), "duration": "2h", "tip": tip}
            if a.get("lng"):
                entry["lng"] = a["lng"]
            if a.get("lat"):
                entry["lat"] = a["lat"]
            day_attractions.append(entry)

        hotel_raw = hotels[0] if hotels else {}
        day_hotel: dict = {
            "name": hotel_raw.get("name", ""),
            "price_per_night": hotel_raw.get("price_per_night", 0),
        }
        if hotel_raw.get("lng"):
            day_hotel["lng"] = hotel_raw["lng"]
        if hotel_raw.get("lat"):
            day_hotel["lat"] = hotel_raw["lat"]

        meal_type_map = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
        day_foods_raw = food_list[(i - 1) * per_day_food: i * per_day_food]
        meals = [
            {
                "type": meal_type_map.get(f.get("meal_type", "lunch"), f.get("meal_type", "午餐")),
                "name": f.get("name", ""),
                "price": f.get("avg_price_per_person", 80),
            }
            for f in day_foods_raw
        ]

        days.append({
            "day": i,
            "date": day_date,
            "attractions": day_attractions,
            "hotel": day_hotel,
            "meals": meals,
            "estimated_cost": round(budget / days_count),
        })

    return {
        "days": days,
        "total_cost": budget,
        "tips": ["提前预订热门景点门票", "注意当地天气变化", "保留部分应急资金"],
    }


async def strategy_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== StrategyAgent：生成完整攻略 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"

    context = _build_context(state, lang)
    system_prompt = _SYSTEM[lang]
    prompt = context + ("\n\n请生成完整攻略：" if lang == "zh" else "\n\nPlease generate the complete travel guide:")

    try:
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, base_url=config.dashscope_api_base, temperature=0.3)
        response = await llm.ainvoke([HumanMessage(content=system_prompt + "\n\n" + prompt)])
        final_plan = response.content if hasattr(response, "content") else str(response)
        logger.info(f"StrategyAgent 完成，攻略长度: {len(final_plan)} 字符")
        structured = _build_structured_plan(state)
        logger.info(f"StrategyAgent 生成 structured_plan，共 {len(structured.get('days', []))} 天")
        return {"final_plan": final_plan, "structured_plan": structured}
    except Exception as e:
        logger.exception("StrategyAgent 失败: {}", repr(e))
        fallback = (f"攻略生成失败，以下是原始数据：\n{context}"
                    if lang == "zh" else f"Guide generation failed. Raw data:\n{context}")
        structured = _build_structured_plan(state)
        return {"final_plan": fallback, "structured_plan": structured, "errors": {"strategy": str(e)}}
