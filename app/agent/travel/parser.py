# app/agent/travel/parser.py
import json
import re
from textwrap import dedent
from typing import Dict, Any

from langchain_core.messages import HumanMessage, SystemMessage
from loguru import logger

from app.core.llm_factory import LLMFactory
from app.agent.travel.state import TravelPlanState, TripParams

_SYSTEM = dedent("""
    你是旅行规划助手。从用户输入中提取旅行参数，以 JSON 格式返回。

    返回格式（只返回 JSON，不加任何说明文字）：
    {
      "destination": "目的地城市",
      "start_date": "YYYY-MM-DD 或空字符串",
      "days": 整数,
      "num_people": 整数,
      "budget": 浮点数,
      "preferences": ["标签1", "标签2"],
      "language": "zh 或 en"
    }

    语言检测规则：
    - 输入主要是英文 → language 设为 "en"
    - 其他情况 → language 设为 "zh"

    无法确定的字段使用默认值：
    - start_date: ""
    - days: 3
    - num_people: 2
    - budget: 3000.0
    - preferences: []
""").strip()


async def _invoke_parser_chain(user_input: str) -> TripParams:
    """Build and execute parsing chain using manual JSON parsing (DeepSeek compatible)."""
    llm = LLMFactory.create_travel_llm(temperature=0)
    messages = [SystemMessage(content=_SYSTEM), HumanMessage(content=user_input)]
    response = await llm.ainvoke(messages)
    content = response.content if hasattr(response, "content") else str(response)

    # Extract JSON object from response
    match = re.search(r"\{.*\}", content, re.DOTALL)
    if not match:
        raise ValueError(f"LLM 未返回有效 JSON: {content[:200]}")

    data = json.loads(match.group())
    return TripParams(**data)


async def parser_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== ParserAgent：解析旅行参数 ===")
    try:
        params = await _invoke_parser_chain(state["user_input"])
        logger.info(f"解析结果: destination={params.destination}, days={params.days}, language={params.language}")
        return {"trip_params": params}
    except Exception as e:
        logger.exception("ParserAgent 失败: {}", repr(e))
        return {
            "trip_params": TripParams(destination="", start_date="", days=3, budget=3000.0),
            "errors": {"parser": str(e)},
        }
