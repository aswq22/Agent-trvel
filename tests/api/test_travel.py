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
        mock_graph.get_state = MagicMock(return_value=MagicMock(
            values={"final_plan": "成都3日游攻略...", "structured_plan": {"days": [], "total_cost": 3000.0, "tips": []}}
        ))
        events = []
        async for event in travel_service.plan(user_input="帮我规划成都3日游"):
            events.append(event)

    assert any(e.get("type") == "complete" for e in events)


@pytest.mark.asyncio
async def test_travel_service_complete_includes_structured_plan():
    from app.services.travel_service import travel_service

    async def mock_stream(*args, **kwargs):
        yield {"strategy_agent": {"final_plan": "攻略", "structured_plan": {"days": [{"day": 1}], "total_cost": 1000.0, "tips": []}}}

    with patch.object(travel_service, "_graph") as mock_graph:
        mock_graph.astream = mock_stream
        mock_graph.get_state = MagicMock(return_value=MagicMock(
            values={"final_plan": "攻略", "structured_plan": {"days": [{"day": 1}], "total_cost": 1000.0, "tips": []}}
        ))
        events = []
        async for event in travel_service.plan(user_input="成都之旅"):
            events.append(event)

    complete = next(e for e in events if e.get("type") == "complete")
    assert complete.get("structured_plan") is not None
    assert complete["structured_plan"]["total_cost"] == 1000.0


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


def test_travel_plan_endpoint_exists():
    import sys
    from unittest.mock import MagicMock

    # Stub out problematic Milvus/numpy chain before importing app.main
    for mod in ["pymilvus", "langchain_milvus", "langchain_milvus.function"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    from fastapi.testclient import TestClient
    from app.main import app
    client = TestClient(app)
    resp = client.post("/api/travel/plan", json={})
    assert resp.status_code != 404


def test_map_key_endpoint():
    import sys
    from unittest.mock import MagicMock, patch
    for mod in ["pymilvus", "langchain_milvus", "langchain_milvus.function"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    from fastapi.testclient import TestClient
    with patch("app.api.travel.config") as api_cfg, \
         patch("app.db.share_store.create_tables"):
        api_cfg.amap_js_key = "test-amap-key"
        from app.main import app
        client = TestClient(app)
        resp = client.get("/api/travel/map-key")
        assert resp.status_code == 200
        assert resp.json()["key"] == "test-amap-key"


def test_share_create_and_read():
    import sys
    from unittest.mock import MagicMock, patch
    for mod in ["pymilvus", "langchain_milvus", "langchain_milvus.function"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    from fastapi.testclient import TestClient
    from app.main import app

    saved = {}

    def fake_save(plan, structured):
        fake_id = "test-share-id-123"
        saved[fake_id] = {"plan": plan, "structured_plan": structured}
        return fake_id

    def fake_get(share_id):
        return saved.get(share_id)

    with patch("app.api.travel.save_share", fake_save), \
         patch("app.api.travel.get_share", fake_get), \
         patch("app.db.share_store.create_tables"):
        client = TestClient(app)
        resp = client.post("/api/travel/share", json={
            "plan": "# 成都攻略",
            "structured_plan": {"days": [], "total_cost": 1000.0, "tips": []}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["share_id"] == "test-share-id-123"
        assert "test-share-id-123" in data["url"]

        resp2 = client.get(f"/api/travel/share/{data['share_id']}")
        assert resp2.status_code == 200
        assert resp2.json()["plan"] == "# 成都攻略"

        resp3 = client.get("/api/travel/share/nonexistent-id")
        assert resp3.status_code == 404
