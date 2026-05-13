import pytest
from pydantic import ValidationError
from app.agent.travel.state import TripParams, TravelPlanState, merge_dicts


def test_trip_params_defaults():
    p = TripParams(destination="成都", budget=3000.0)
    assert p.days == 3
    assert p.num_people == 2
    assert p.language == "zh"
    assert p.preferences == []


def test_trip_params_requires_destination():
    with pytest.raises(ValidationError):
        TripParams(budget=3000.0)  # destination is required


def test_trip_params_english():
    p = TripParams(destination="Chengdu", budget=500.0, language="en")
    assert p.language == "en"


def test_merge_dicts():
    a = {"parser": "err1"}
    b = {"attraction": "err2"}
    result = merge_dicts(a, b)
    assert result == {"parser": "err1", "attraction": "err2"}


def test_merge_dicts_overwrite():
    a = {"key": "old"}
    b = {"key": "new"}
    assert merge_dicts(a, b) == {"key": "new"}


def test_travel_plan_state_typing():
    from app.agent.travel.state import TravelPlanState
    state: TravelPlanState = {
        "user_input": "test",
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "structured_plan": None,
        "errors": {},
        "messages": [],
    }
    assert state["user_input"] == "test"


def test_travel_mcp_servers_config():
    from app.config import config
    servers = config.travel_mcp_servers
    assert "gaode" in servers
    assert "ctrip" in servers
    assert "dianping" in servers
    for s in servers.values():
        assert "transport" in s
        assert "url" in s


def test_travel_plan_state_structured_plan():
    # None is valid (before strategy runs)
    state: TravelPlanState = {
        "user_input": "test",
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "structured_plan": None,
        "errors": {},
        "messages": [],
    }
    assert state.get("structured_plan") is None

    # dict value is also valid (after strategy runs)
    state["structured_plan"] = {"days": [{"day": 1}], "total_cost": 3000.0, "tips": []}
    assert state["structured_plan"]["total_cost"] == 3000.0
    assert len(state["structured_plan"]["days"]) == 1
