# app/agent/travel/geo_utils.py
"""Gaode REST API coordinate fill for items missing lng/lat."""
import asyncio
from typing import List

import httpx
from loguru import logger

_GAODE_POI_URL = "https://restapi.amap.com/v3/place/text"


async def _lookup_one(client: httpx.AsyncClient, name: str, city: str, api_key: str) -> tuple[float, float] | None:
    try:
        resp = await client.get(
            _GAODE_POI_URL,
            params={"keywords": name, "city": city, "key": api_key, "output": "json", "offset": 1},
            timeout=5.0,
        )
        data = resp.json()
        if data.get("status") == "1" and data.get("pois"):
            lng_str, lat_str = data["pois"][0]["location"].split(",")
            return float(lng_str), float(lat_str)
    except Exception as e:
        logger.debug("坐标补全失败 [{}]: {}", name, e)
    return None


async def fill_coordinates(items: List[dict], city: str, api_key: str) -> List[dict]:
    """Fill missing lng/lat for each item via Gaode POI search (concurrent)."""
    if not api_key or not items:
        return items

    missing = [(i, item) for i, item in enumerate(items) if not item.get("lng") or not item.get("lat")]
    if not missing:
        return items

    async with httpx.AsyncClient() as client:
        tasks = [
            _lookup_one(client, item.get("name") or item.get("address", ""), city, api_key)
            for _, item in missing
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    for (i, item), result in zip(missing, results):
        if isinstance(result, tuple):
            item["lng"], item["lat"] = result
            logger.debug("坐标已补全 [{}]: {},{}", item.get("name"), item["lng"], item["lat"])

    return items
