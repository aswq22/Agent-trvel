# tests/agent/travel/test_agents.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.travel.state import TravelPlanState, TripParams


def _make_full_state(destination="成都", days=3, language="zh") -> TravelPlanState:
    return {
        "user_input": "test",
        "trip_params": TripParams(destination=destination, days=days, budget=3000.0, language=language),
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }


@pytest.mark.asyncio
async def test_attraction_agent_returns_list():
    from app.agent.travel.attraction import attraction_node

    mock_tools = []
    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '[{"name": "大熊猫基地", "address": "成华区", "rating": 4.9, "reason": "必去"}]'

    with patch("app.agent.travel.attraction.get_travel_mcp_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=mock_tools)
        mock_client_fn.return_value = mock_client
        with patch("app.agent.travel.attraction.ChatQwen") as MockLLM:
            mock_llm_instance = MagicMock()
            mock_llm_instance.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance
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

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '{"days": [{"day": 1, "attractions": ["大熊猫基地"], "transport": "地铁"}]}'

    with patch("app.agent.travel.route.get_travel_mcp_client") as mock_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        with patch("app.agent.travel.route.ChatQwen") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm
            result = await route_node(state)

    assert "route" in result
    assert isinstance(result["route"], dict)


@pytest.mark.asyncio
async def test_hotel_agent_returns_list():
    from app.agent.travel.hotel import hotel_node

    state = _make_full_state()
    state["attractions"] = [{"name": "大熊猫基地", "address": "成华区锦官路"}]

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '[{"name": "香格里拉酒店", "price_per_night": 1200, "rating": 4.9}]'

    with patch("app.agent.travel.hotel.get_travel_mcp_client") as mock_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        with patch("app.agent.travel.hotel.ChatQwen") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm
            result = await hotel_node(state)

    assert "hotels" in result
    assert isinstance(result["hotels"], list)


@pytest.mark.asyncio
async def test_food_agent_returns_list():
    from app.agent.travel.food import food_node

    state = _make_full_state()
    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '[{"name": "大龙燚火锅", "cuisine": "火锅", "avg_price": 120}]'

    with patch("app.agent.travel.food.get_travel_mcp_client") as mock_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        with patch("app.agent.travel.food.ChatQwen") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm
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
    state["foods"] = [{"name": "大龙燚火锅", "meal_type": "dinner"}]

    mock_response = MagicMock()
    mock_response.content = "# 成都3日游攻略\n\n## Day 1\n大熊猫基地..."

    with patch("app.agent.travel.strategy.ChatQwen") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
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

    mock_response = MagicMock()
    mock_response.content = "# Chengdu 3-Day Travel Guide\n\n## Day 1..."

    with patch("app.agent.travel.strategy.ChatQwen") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result = await strategy_node(state)

    assert "final_plan" in result
