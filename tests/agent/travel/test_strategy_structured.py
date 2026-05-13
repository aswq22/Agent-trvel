# tests/agent/travel/test_strategy_structured.py
import pytest
from app.agent.travel.strategy import _build_structured_plan
from app.agent.travel.state import TripParams


def _make_state(days=2, attractions=None, hotels=None, foods=None, start_date="2026-06-01"):
    params = TripParams(destination="成都", days=days, budget=2000.0, start_date=start_date)
    return {
        "user_input": "test",
        "trip_params": params,
        "attractions": attractions or [],
        "route": {},
        "hotels": hotels or [],
        "foods": foods or [],
        "final_plan": "",
        "structured_plan": None,
        "errors": {},
        "messages": [],
    }


def test_build_structured_plan_basic():
    state = _make_state(days=2)
    result = _build_structured_plan(state)
    assert "days" in result
    assert len(result["days"]) == 2
    assert result["total_cost"] == 2000.0
    assert "tips" in result


def test_build_structured_plan_dates():
    state = _make_state(days=3, start_date="2026-06-01")
    result = _build_structured_plan(state)
    assert result["days"][0]["date"] == "2026-06-01"
    assert result["days"][1]["date"] == "2026-06-02"
    assert result["days"][2]["date"] == "2026-06-03"


def test_build_structured_plan_distributes_attractions():
    attractions = [
        {"name": "宽窄巷子", "highlights": "历史街区", "lng": 104.06, "lat": 30.67},
        {"name": "锦里", "highlights": "民俗文化"},
        {"name": "武侯祠", "highlights": "三国文化"},
        {"name": "春熙路", "highlights": "购物"},
    ]
    state = _make_state(days=2, attractions=attractions)
    result = _build_structured_plan(state)
    assert len(result["days"][0]["attractions"]) == 2
    assert len(result["days"][1]["attractions"]) == 2


def test_build_structured_plan_coordinates_included():
    attractions = [{"name": "宽窄巷子", "highlights": [], "lng": 104.06, "lat": 30.67}]
    state = _make_state(days=1, attractions=attractions)
    result = _build_structured_plan(state)
    attr = result["days"][0]["attractions"][0]
    assert attr["lng"] == 104.06
    assert attr["lat"] == 30.67


def test_build_structured_plan_no_trip_params():
    state = _make_state()
    state["trip_params"] = None
    result = _build_structured_plan(state)
    assert result == {}


def test_build_structured_plan_no_start_date():
    state = _make_state(days=2, start_date="")
    result = _build_structured_plan(state)
    assert result["days"][0]["date"] == "第1天"
    assert result["days"][1]["date"] == "第2天"
