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
        return {"final_plan": final_plan}
    except Exception as e:
        logger.exception("StrategyAgent 失败: {}", repr(e))
        fallback = (f"攻略生成失败，以下是原始数据：\n{context}"
                    if lang == "zh" else f"Guide generation failed. Raw data:\n{context}")
        return {"final_plan": fallback, "errors": {"strategy": str(e)}}
