# mcp_servers/meituan.py
# 美团开放平台接入（需企业资质，申请地址：https://open.meituan.com）
# 接口签名文档：https://developer.meituan.com/docs/auth
# 此文件提供与 dianping.py / ctrip.py 完全相同的工具接口，可直接替换
#
# 使用方式：
#   1. 申请到美团 appKey 和 appSecret 后填入 .env
#   2. 将 config.py 中 mcp_dianping_url 和 mcp_ctrip_url 指向本服务端口
#   3. python mcp_servers/meituan.py  （默认端口 8013，可同时运行不冲突）
from typing import Optional
import hashlib
import time
import httpx
from fastmcp import FastMCP
from app.config import config

mcp = FastMCP("Meituan")

MEITUAN_BASE = "https://api.meituan.com"


def _sign(params: dict, app_secret: str) -> str:
    """美团 API 签名（md5(appSecret + sorted key=value + appSecret)）"""
    sorted_params = "".join(f"{k}{v}" for k, v in sorted(params.items()))
    raw = app_secret + sorted_params + app_secret
    return hashlib.md5(raw.encode()).hexdigest()


async def _meituan_request(endpoint: str, params: dict) -> dict:
    app_key = config.meituan_app_key        # 需在 config.py 中添加
    app_secret = config.meituan_app_secret  # 需在 config.py 中添加
    params.update({"appkey": app_key, "timestamp": int(time.time())})
    params["sign"] = _sign(params, app_secret)
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(f"{MEITUAN_BASE}{endpoint}", params=params)
        resp.raise_for_status()
        return resp.json()


# ──────────────────────────────────────────────────────────────────────────────
# 景点 & 餐厅工具（替代 dianping.py，接口名称完全一致）
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def dianping_attraction_search(
    city: str,
    keywords: str = "",
    tags: Optional[str] = None,
    max_ticket_price: Optional[float] = None,
) -> dict:
    """搜索景点（美团/大众点评真实数据）

    Args:
        city: 城市名
        keywords: 景点关键词
        tags: 标签筛选（逗号分隔）
        max_ticket_price: 最高票价（元）
    """
    # 美团 POI 搜索接口（景点类）
    # 文档参考：https://developer.meituan.com/docs/poi-search
    params = {
        "city": city,
        "keyword": keywords or f"{city}景点",
        "category": "scenic",   # 景点类别
        "limit": 20,
    }
    if max_ticket_price is not None:
        params["max_price"] = max_ticket_price

    data = await _meituan_request("/poi/v1/search", params)

    attractions = [
        {
            "id": poi.get("poi_id", ""),
            "name": poi.get("name", ""),
            "rating": poi.get("avg_score", 0.0),
            "review_count": poi.get("comment_num", 0),
            "ticket_price": poi.get("lowest_price", 0.0),
            "address": poi.get("address", ""),
            "lat": poi.get("latitude", 0.0),
            "lng": poi.get("longitude", 0.0),
            "tags": poi.get("tag_list", []),
            "open_hours": poi.get("open_time", ""),
            "highlights": poi.get("alias_name", poi.get("name", "")),
        }
        for poi in data.get("data", {}).get("list", [])
    ]

    return {"status": "success", "source": "meituan_realtime",
            "city": city, "total": len(attractions), "attractions": attractions}


@mcp.tool()
async def dianping_restaurant_search(
    city: str,
    area: str = "",
    cuisine: str = "",
    max_price_per_person: Optional[float] = None,
) -> dict:
    """搜索餐厅（美团/大众点评真实数据）

    Args:
        city: 城市名
        area: 区域，如 "锦江区"
        cuisine: 菜系，如 "火锅"、"川菜"
        max_price_per_person: 人均最高价格（元）
    """
    params = {
        "city": city,
        "keyword": cuisine or "餐厅",
        "category": "food",
        "district": area,
        "limit": 20,
    }
    if max_price_per_person is not None:
        params["max_avg_price"] = max_price_per_person

    data = await _meituan_request("/poi/v1/search", params)

    restaurants = [
        {
            "id": poi.get("poi_id", ""),
            "name": poi.get("name", ""),
            "rating": poi.get("avg_score", 0.0),
            "review_count": poi.get("comment_num", 0),
            "cuisine": poi.get("category_name", cuisine),
            "avg_price_per_person": poi.get("avg_price", 0.0),
            "address": poi.get("address", ""),
            "lat": poi.get("latitude", 0.0),
            "lng": poi.get("longitude", 0.0),
            "open_hours": poi.get("open_time", ""),
            "signature_dishes": poi.get("recommend_foods", []),
        }
        for poi in data.get("data", {}).get("list", [])
    ]

    return {"status": "success", "source": "meituan_realtime",
            "city": city, "total": len(restaurants), "restaurants": restaurants}


@mcp.tool()
async def dianping_menu(restaurant_id: str) -> dict:
    """获取餐厅菜单（美团真实数据）

    Args:
        restaurant_id: 餐厅 POI ID
    """
    data = await _meituan_request("/poi/v1/menu", {"poi_id": restaurant_id})
    menu = data.get("data", {})
    dishes = menu.get("recommend_dishes", [])
    return {
        "status": "success",
        "restaurant_id": restaurant_id,
        "signature_dishes": [d.get("name") for d in dishes],
        "must_try": dishes[0].get("name") if dishes else "",
        "menu": dishes,
    }


# ──────────────────────────────────────────────────────────────────────────────
# 酒店工具（替代 ctrip.py，接口名称完全一致）
# ──────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def ctrip_hotel_search(
    city: str,
    check_in: str,
    check_out: str,
    max_price_per_night: Optional[float] = None,
    min_stars: Optional[int] = None,
    district: Optional[str] = None,
) -> dict:
    """搜索酒店（美团酒旅真实数据，含实时价格）

    Args:
        city: 城市名
        check_in: 入住日期 YYYY-MM-DD
        check_out: 退房日期 YYYY-MM-DD
        max_price_per_night: 每晚最高价格（元）
        min_stars: 最低星级（1-5）
        district: 区域，如 "锦江区"
    """
    params = {
        "city": city,
        "check_in": check_in,
        "check_out": check_out,
        "limit": 20,
    }
    if max_price_per_night:
        params["max_price"] = max_price_per_night
    if min_stars:
        params["star_level"] = min_stars
    if district:
        params["district"] = district

    data = await _meituan_request("/hotel/v1/search", params)

    hotels = [
        {
            "hotel_id": h.get("hotel_id", ""),
            "name": h.get("hotel_name", ""),
            "stars": h.get("star_level", 3),
            "rating": h.get("score", 0.0),
            "price_per_night": h.get("lowest_price", 0.0),
            "address": h.get("address", ""),
            "lat": h.get("latitude", 0.0),
            "lng": h.get("longitude", 0.0),
            "district": h.get("district", ""),
            "amenities": h.get("facilities", []),
        }
        for h in data.get("data", {}).get("hotel_list", [])
    ]

    return {"status": "success", "source": "meituan_realtime",
            "city": city, "check_in": check_in, "check_out": check_out,
            "total": len(hotels), "hotels": hotels}


@mcp.tool()
async def ctrip_hotel_detail(hotel_id: str) -> dict:
    """获取酒店详情及实时房型价格（美团酒旅）

    Args:
        hotel_id: 酒店 ID
    """
    data = await _meituan_request("/hotel/v1/detail", {"hotel_id": hotel_id})
    hotel = data.get("data", {})
    return {
        "status": "success",
        "hotel": hotel,
        "room_types": hotel.get("room_list", []),
        "policies": {
            "check_in": hotel.get("check_in_time", "14:00"),
            "check_out": hotel.get("check_out_time", "12:00"),
            "cancel": hotel.get("cancel_policy", ""),
        },
    }


if __name__ == "__main__":
    # 默认端口 8013；如需替换 dianping(:8012)/ctrip(:8011)，改对应端口
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8013)
