# mcp_servers/gaode_maps.py
import httpx
from fastmcp import FastMCP
from app.config import config

mcp = FastMCP("GaodeMaps")

GAODE_BASE = "https://restapi.amap.com"


@mcp.tool()
async def gaode_poi_search(keywords: str, city: str, types: str = "风景名胜") -> dict:
    """搜索高德地图 POI 兴趣点（景点、餐厅等）

    Args:
        keywords: 搜索关键词，如 "大熊猫基地"
        city: 城市名，如 "成都"
        types: POI 类型，默认 "风景名胜"，可用 "餐饮服务"

    Returns:
        高德 API 返回的 POI 列表
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GAODE_BASE}/v3/place/text",
            params={
                "keywords": keywords,
                "city": city,
                "types": types,
                "key": config.gaode_api_key,
                "output": "json",
                "offset": 20,
                "extensions": "all",
            },
        )
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def gaode_route_plan(
    origin: str,
    destination: str,
    waypoints: str = "",
    strategy: int = 0,
) -> dict:
    """规划驾车路线

    Args:
        origin: 出发地经纬度，格式 "116.481028,39.989643"
        destination: 目的地经纬度，格式 "116.434446,39.90816"
        waypoints: 途经点经纬度（多个用 ";" 分隔），可为空
        strategy: 路线策略：0=速度优先, 1=费用优先, 2=距离优先

    Returns:
        路线规划结果，含距离、时间、路线描述
    """
    params: dict = {
        "origin": origin,
        "destination": destination,
        "strategy": strategy,
        "key": config.gaode_api_key,
        "output": "json",
    }
    if waypoints:
        params["waypoints"] = waypoints

    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{GAODE_BASE}/v5/direction/driving", params=params)
        resp.raise_for_status()
        return resp.json()


@mcp.tool()
async def gaode_distance_matrix(origins: str, destinations: str) -> dict:
    """计算多点间驾车距离矩阵（用于优化景点访问顺序）

    Args:
        origins: 出发地经纬度，多个用 "|" 分隔，如 "116.481,39.990|116.434,39.908"
        destinations: 目的地经纬度，多个用 "|" 分隔

    Returns:
        距离矩阵，含各点对间的距离（米）和时间（秒）
    """
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GAODE_BASE}/v5/direction/matrix/driving",
            params={
                "origins": origins,
                "destinations": destinations,
                "key": config.gaode_api_key,
                "output": "json",
            },
        )
        resp.raise_for_status()
        return resp.json()


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8010)
