# tests/api/test_travel.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_travel_service_yields_complete_event():
    from app.services.travel_service import travel_service

    async def mock_stream(*args, **kwargs):
        yield {"strategy_agent": {"final_plan": "成都3日游攻略..."}}

    with patch.object(travel_service, "_graph") as mock_graph:
        mock_graph.astream = mock_stream
        mock_graph.get_state = MagicMock(return_value=MagicMock(values={"final_plan": "成都3日游攻略..."}))
        events = []
        async for event in travel_service.plan(user_input="帮我规划成都3日游"):
            events.append(event)

    assert any(e.get("type") == "complete" for e in events)


def test_trip_request_model():
    from app.models.travel import TripRequest
    req = TripRequest(user_input="帮我规划成都之旅")
    assert req.user_input == "帮我规划成都之旅"
    assert req.trip_params is None


def test_trip_request_with_params():
    from app.models.travel import TripRequest
    from app.agent.travel.state import TripParams
    params = TripParams(destination="成都", budget=5000.0)
    req = TripRequest(trip_params=params)
    assert req.trip_params.destination == "成都"
