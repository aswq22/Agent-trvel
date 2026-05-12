# tests/agent/travel/test_parser.py
import pytest
from unittest.mock import AsyncMock, patch
from app.agent.travel.state import TravelPlanState, TripParams
from app.agent.travel.parser import parser_node


def _make_state(user_input: str) -> TravelPlanState:
    return {
        "user_input": user_input,
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }


@pytest.mark.asyncio
async def test_parser_returns_trip_params():
    mock_params = TripParams(destination="成都", days=5, budget=5000.0, preferences=["美食", "历史"])
    with patch("app.agent.travel.parser._invoke_parser_chain", new=AsyncMock(return_value=mock_params)):
        state = _make_state("帮我规划5天成都之旅，预算5000元，喜欢美食和历史")
        result = await parser_node(state)
    assert "trip_params" in result
    assert result["trip_params"].destination == "成都"


@pytest.mark.asyncio
async def test_parser_fallback_on_error():
    with patch("app.agent.travel.parser._invoke_parser_chain",
               new=AsyncMock(side_effect=Exception("LLM error"))):
        state = _make_state("garbage input")
        result = await parser_node(state)
    assert "trip_params" in result
    assert "parser" in result.get("errors", {})


@pytest.mark.asyncio
async def test_parser_detects_english():
    mock_params = TripParams(destination="Chengdu", days=4, budget=500.0, language="en")
    with patch("app.agent.travel.parser._invoke_parser_chain", new=AsyncMock(return_value=mock_params)):
        state = _make_state("Plan a 4-day trip to Chengdu, budget $500")
        result = await parser_node(state)
    assert result["trip_params"].language == "en"
