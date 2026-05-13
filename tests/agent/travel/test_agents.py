# tests/agent/travel/test_agents.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.travel.state import TravelPlanState, TripParams

_LLM_PATCH = "app.core.llm_factory.LLMFactory.create_travel_llm"


def _make_full_state(destination="成都", days=3, language="zh") -> TravelPlanState:
    return {
        "user_input": "test",
        "trip_params": TripParams(destination=destination, days=days, budget=3000.0, language=language),
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "structured_plan": None,
        "errors": {},
        "messages": [],
    }


def _mock_llm(content: str):
    """Return a mock LLM that yields `content` on ainvoke."""
    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = content
    llm = MagicMock()
    llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
    llm.ainvoke = AsyncMock(return_value=mock_response)
    return llm


@pytest.mark.asyncio
async def test_attraction_agent_returns_list():
    from app.agent.travel.attraction import attraction_node

    with patch("app.agent.travel.attraction.get_travel_mcp_client") as mock_client_fn, \
         patch(_LLM_PATCH, return_value=_mock_llm('[{"name": "大熊猫基地", "address": "成华区", "rating": 4.9, "reason": "必去"}]')):
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_client_fn.return_value = mock_client
        result = await attraction_node(_make_full_state())

    assert "attractions" in result
    assert isinstance(result["attractions"], list)


@pytest.mark.asyncio
async def test_attraction_agent_graceful_on_mcp_error():
    from app.agent.travel.attraction import attraction_node

    with patch("app.agent.travel.attraction.get_travel_mcp_client", side_effect=Exception("MCP down")):
        result = await attraction_node(_make_full_state())

    assert "errors" in result
    assert "attraction" in result["errors"]
    assert result["attractions"] == []


@pytest.mark.asyncio
async def test_route_agent_returns_dict():
    from app.agent.travel.route import route_node

    state = _make_full_state()
    state["attractions"] = [
        {"name": "大熊猫基地", "address": "成华区", "lat": 30.7376, "lng": 104.1393},
        {"name": "宽窄巷子", "address": "青羊区", "lat": 30.6665, "lng": 104.0490},
    ]

    content = '{"days": [{"day": 1, "attractions": ["大熊猫基地"], "transport": "地铁"}]}'
    with patch("app.agent.travel.route.get_travel_mcp_client") as mock_fn, \
         patch(_LLM_PATCH, return_value=_mock_llm(content)):
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        result = await route_node(state)

    assert "route" in result
    assert isinstance(result["route"], dict)


@pytest.mark.asyncio
async def test_hotel_agent_returns_list():
    from app.agent.travel.hotel import hotel_node

    state = _make_full_state()
    state["attractions"] = [{"name": "大熊猫基地", "address": "成华区锦官路"}]

    content = '[{"name": "香格里拉酒店", "price_per_night": 1200, "rating": 4.9}]'
    with patch("app.agent.travel.hotel.get_travel_mcp_client") as mock_fn, \
         patch(_LLM_PATCH, return_value=_mock_llm(content)):
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        result = await hotel_node(state)

    assert "hotels" in result
    assert isinstance(result["hotels"], list)


@pytest.mark.asyncio
async def test_food_agent_returns_list():
    from app.agent.travel.food import food_node

    state = _make_full_state()
    content = '[{"name": "大龙燚火锅", "cuisine": "火锅", "avg_price_per_person": 120}]'
    with patch("app.agent.travel.food.get_travel_mcp_client") as mock_fn, \
         patch(_LLM_PATCH, return_value=_mock_llm(content)):
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        result = await food_node(state)

    assert "foods" in result
    assert isinstance(result["foods"], list)


@pytest.mark.asyncio
async def test_strategy_agent_returns_plan():
    from app.agent.travel.strategy import strategy_node

    state = _make_full_state()
    state["attractions"] = [{"name": "大熊猫基地"}]
    state["route"] = {"days": [{"day": 1, "attractions": ["大熊猫基地"]}]}
    state["hotels"] = [{"name": "香格里拉酒店", "price_per_night": 1200}]
    state["foods"] = [{"name": "大龙燚火锅"}]

    content = "# 成都3日游攻略\n\n## Day 1\n大熊猫基地..."
    with patch(_LLM_PATCH, return_value=_mock_llm(content)):
        result = await strategy_node(state)

    assert "final_plan" in result
    assert len(result["final_plan"]) > 0


@pytest.mark.asyncio
async def test_strategy_agent_english_output():
    from app.agent.travel.strategy import strategy_node

    state = _make_full_state(language="en")
    state["route"] = {}
    state["hotels"] = []
    state["foods"] = []

    content = "# Chengdu 3-Day Travel Guide\n\n## Day 1..."
    with patch(_LLM_PATCH, return_value=_mock_llm(content)):
        result = await strategy_node(state)

    assert "final_plan" in result


@pytest.mark.asyncio
async def test_graph_build():
    from app.agent.travel.graph import build_travel_graph
    graph = build_travel_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_initial_state_shape():
    from app.agent.travel.graph import make_initial_state
    state = make_initial_state("帮我规划成都3日游")
    assert state["user_input"] == "帮我规划成都3日游"
    assert state["attractions"] == []
    assert state["errors"] == {}
