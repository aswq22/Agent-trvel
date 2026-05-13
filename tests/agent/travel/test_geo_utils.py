# tests/agent/travel/test_geo_utils.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_fill_coordinates_skips_when_no_api_key():
    from app.agent.travel.geo_utils import fill_coordinates
    items = [{"name": "宽窄巷子"}]
    result = await fill_coordinates(items, "成都", "")
    assert result[0].get("lng") is None


@pytest.mark.asyncio
async def test_fill_coordinates_skips_existing():
    from app.agent.travel.geo_utils import fill_coordinates
    items = [{"name": "宽窄巷子", "lng": 104.06, "lat": 30.67}]
    result = await fill_coordinates(items, "成都", "fake-key")
    # Should not touch items that already have coordinates (no HTTP calls)
    assert result[0]["lng"] == 104.06


@pytest.mark.asyncio
async def test_fill_coordinates_fills_missing(httpx_mock=None):
    from app.agent.travel.geo_utils import fill_coordinates

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "status": "1",
        "pois": [{"location": "104.0617,30.6701"}],
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        items = [{"name": "宽窄巷子"}]
        result = await fill_coordinates(items, "成都", "fake-key")

    assert result[0]["lng"] == pytest.approx(104.0617)
    assert result[0]["lat"] == pytest.approx(30.6701)


@pytest.mark.asyncio
async def test_fill_coordinates_handles_api_failure():
    from app.agent.travel.geo_utils import fill_coordinates

    mock_response = MagicMock()
    mock_response.json.return_value = {"status": "0", "pois": []}

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, return_value=mock_response):
        items = [{"name": "不存在的地方"}]
        result = await fill_coordinates(items, "成都", "fake-key")

    # Should not crash, item unchanged
    assert result[0].get("lng") is None


@pytest.mark.asyncio
async def test_fill_coordinates_handles_exception():
    from app.agent.travel.geo_utils import fill_coordinates

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock, side_effect=Exception("network error")):
        items = [{"name": "宽窄巷子"}]
        result = await fill_coordinates(items, "成都", "fake-key")

    # Should not crash
    assert result[0].get("lng") is None
