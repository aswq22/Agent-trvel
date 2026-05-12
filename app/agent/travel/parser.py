# app/agent/travel/parser.py
from textwrap import dedent
from typing import Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState, TripParams

_SYSTEM = dedent("""
    你是旅行规划助手。从用户输入中提取旅行参数，填充到指定结构中。

    语言检测规则：
    - 输入主要是英文 → language 设为 "en"
    - 其他情况 → language 设为 "zh"

    无法确定的字段使用默认值：
    - start_date: ""（留空）
    - days: 3
    - num_people: 2
    - budget: 3000.0
    - preferences: []
""").strip()

_parser_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", "{user_input}"),
])


async def _invoke_parser_chain(user_input: str) -> TripParams:
    """Build and execute parsing chain; extracted for testability."""
    llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
    chain = _parser_prompt | llm.with_structured_output(TripParams)
    return await chain.ainvoke({"user_input": user_input})


async def parser_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== ParserAgent：解析旅行参数 ===")
    try:
        params = await _invoke_parser_chain(state["user_input"])
        logger.info(f"解析结果: destination={params.destination}, days={params.days}, language={params.language}")
        return {"trip_params": params}
    except Exception as e:
        logger.error(f"ParserAgent 失败: {e}", exc_info=True)
        return {
            "trip_params": TripParams(destination="", start_date="", days=3, budget=3000.0),
            "errors": {"parser": str(e)},
        }
