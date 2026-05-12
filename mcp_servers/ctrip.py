# mcp_servers/ctrip.py
# 使用高德地图 POI API 提供真实酒店数据（高德住宿类 POI 覆盖全国酒店）
# 高德 POI 类型代码: 070000=住宿服务, 070100=宾馆酒店, 070200=旅馆招待所
# API 文档: https://lbs.amap.com/api/webservice/guide/api/search
from typing import Optional
import httpx
from fastmcp import FastMCP
from app.config import config

mcp = FastMCP("Ctrip")

GAODE_BASE = "https://restapi.amap.com"
_HOTEL_TYPES = "070000"   # 住宿服务（含酒店、民宿、青旅等）

# 星级关键词映射（高德无直接星级筛选，通过关键词辅助）
_STAR_KEYWORDS = {
    5: "五星级酒店",
    4: "四星级酒店",
    3: "经济型酒店",
}

# 无 API Key 时的 Mock 降级数据
_MOCK_HOTELS = [
    {
        "hotel_id": "CD001",
        "name": "成都香格里拉大酒店",
        "stars": 5,
        "rating": 4.9,
        "price_per_night": 1200.0,
        "address": "锦江区滨江东路9号",
        "lat": 30.5728,
        "lng": 104.0668,
        "district": "锦江区",
        "amenities": ["免费WiFi", "游泳池", "健身房", "停车场", "行政酒廊"],
    },
    {
        "hotel_id": "CD002",
        "name": "成都宽窄巷子精品民宿",
        "stars": 4,
        "rating": 4.8,
        "price_per_night": 380.0,
        "address": "青羊区宽巷子38号",
        "lat": 30.6665,
        "lng": 104.0490,
        "district": "青羊区",
        "amenities": ["免费WiFi", "早餐", "停车场"],
    },
    {
        "hotel_id": "CD003",
        "name": "成都IFS洲际酒店",
        "stars": 5,
        "rating": 4.9,
        "price_per_night": 880.0,
        "address": "锦江区红星路三段1号",
        "lat": 30.6570,
        "lng": 104.0831,
        "district": "锦江区",
        "amenities": ["免费WiFi", "游泳池", "健身房", "停车场", "SPA"],
    },
    {
        "hotel_id": "CD004",
        "name": "成都春熙路全季酒店",
        "stars": 3,
        "rating": 4.6,
        "price_per_night": 280.0,
        "address": "锦江区春熙路南一段",
        "lat": 30.6590,
        "lng": 104.0804,
        "district": "锦江区",
        "amenities": ["免费WiFi", "停车场"],
    },
]


def _parse_location(location_str: str) -> tuple[float, float]:
    try:
        lng, lat = location_str.split(",")
        return float(lat), float(lng)
    except Exception:
        return 0.0, 0.0


def _gaode_poi_to_hotel(poi: dict, idx: int) -> dict:
    lat, lng = _parse_location(poi.get("location", "0,0"))
    biz = poi.get("biz_ext", {}) or {}
    rating_raw = biz.get("rating", "") or ""
    cost_raw = biz.get("cost", "") or "0"
    name = poi.get("name", "")

    try:
        rating = float(rating_raw)
    except (ValueError, TypeError):
        rating = 4.0

    try:
        price = float(cost_raw)
    except (ValueError, TypeError):
        price = 0.0

    # 从名称推断星级（粗略判断）
    stars = 3
    if any(kw in name for kw in ["香格里拉", "四季", "丽思卡尔顿", "洲际", "万豪", "希尔顿"]):
        stars = 5
    elif any(kw in name for kw in ["万达", "维也纳", "宜必思", "汉庭", "如家"]):
        stars = 3
    elif any(kw in name for kw in ["全季", "亚朵", "桔子水晶"]):
        stars = 4

    address = poi.get("address", "")
    district = address.split("区")[0] + "区" if "区" in address else poi.get("adname", "")

    return {
        "hotel_id": f"GH{idx:04d}",
        "name": name,
        "stars": stars,
        "rating": rating,
        "price_per_night": price,
        "address": address,
        "lat": lat,
        "lng": lng,
        "district": district,
        "amenities": ["免费WiFi"],
        "tel": poi.get("tel", ""),
    }


async def _gaode_hotel_search(keywords: str, city: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GAODE_BASE}/v3/place/text",
            params={
                "keywords": keywords,
                "city": city,
                "types": _HOTEL_TYPES,
                "key": config.gaode_api_key,
                "output": "json",
                "offset": 25,
                "extensions": "all",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1":
            return data.get("pois", [])
        return []


@mcp.tool()
async def ctrip_hotel_search(
    city: str,
    check_in: str,
    check_out: str,
    max_price_per_night: Optional[float] = None,
    min_stars: Optional[int] = None,
    district: Optional[str] = None,
) -> dict:
    """搜索酒店（优先调用高德真实数据，无 API Key 时降级为 Mock 数据）

    Args:
        city: 城市名，如 "成都"、"北京"、"上海"（支持全国所有城市）
        check_in: 入住日期，格式 YYYY-MM-DD
        check_out: 退房日期，格式 YYYY-MM-DD
        max_price_per_night: 每晚最高价格（元），为空不限
        min_stars: 最低星级（1-5），为空不限
        district: 区域筛选，如 "锦江区"，为空不限

    Returns:
        符合条件的酒店列表
    """
    if config.gaode_api_key:
        try:
            # 根据星级偏好选择搜索关键词
            if min_stars and min_stars >= 5:
                keywords = f"{city}五星级酒店"
            elif min_stars and min_stars >= 4:
                keywords = f"{city}四星级酒店"
            elif district:
                keywords = f"{district}酒店"
            else:
                keywords = f"{city}酒店"

            pois = await _gaode_hotel_search(keywords, city)
            hotels = [_gaode_poi_to_hotel(p, i) for i, p in enumerate(pois)]

            # 应用筛选条件
            if min_stars is not None:
                hotels = [h for h in hotels if h["stars"] >= min_stars]
            if max_price_per_night is not None:
                # 高德价格数据不完整，只筛选有价格且在范围内的
                hotels = [h for h in hotels
                          if h["price_per_night"] == 0
                          or h["price_per_night"] <= max_price_per_night]
            if district:
                hotels = [h for h in hotels if district in h.get("district", "")
                          or district in h.get("address", "")]

            return {
                "status": "success",
                "source": "gaode_realtime",
                "city": city,
                "check_in": check_in,
                "check_out": check_out,
                "total": len(hotels),
                "hotels": hotels,
                "note": "价格数据来自高德，实际价格请以携程/美团/官网为准",
            }
        except Exception:
            pass

    # Mock 降级
    hotels = list(_MOCK_HOTELS)
    if max_price_per_night is not None:
        hotels = [h for h in hotels if h["price_per_night"] <= max_price_per_night]
    if min_stars is not None:
        hotels = [h for h in hotels if h["stars"] >= min_stars]
    if district:
        hotels = [h for h in hotels if district in h.get("district", "")]

    return {
        "status": "success",
        "source": "mock",
        "city": city,
        "check_in": check_in,
        "check_out": check_out,
        "total": len(hotels),
        "hotels": hotels,
    }


@mcp.tool()
async def ctrip_hotel_detail(hotel_id: str) -> dict:
    """获取酒店详细信息及房型

    Args:
        hotel_id: 酒店 ID（从 ctrip_hotel_search 返回）

    Returns:
        酒店详情，含房型、价格、设施
    """
    # 高德实时数据的酒店 ID 格式为 GH****
    if hotel_id.startswith("GH"):
        return {
            "status": "success",
            "hotel_id": hotel_id,
            "note": "高德实时酒店详情请通过携程/美团/酒店官网查询房型和实时价格",
            "room_types": [
                {"type": "标准房", "bed": "大床或双床", "price": "请查询官网"},
            ],
            "policies": {"check_in": "14:00", "check_out": "12:00"},
        }

    # Mock 数据酒店
    for h in _MOCK_HOTELS:
        if h["hotel_id"] == hotel_id:
            return {
                "status": "success",
                "hotel": h,
                "room_types": [
                    {"type": "标准双人间", "bed": "两张单床", "area": "28㎡",
                     "price": h["price_per_night"]},
                    {"type": "豪华大床房", "bed": "一张大床", "area": "36㎡",
                     "price": h["price_per_night"] * 1.3},
                ],
                "policies": {
                    "check_in": "14:00",
                    "check_out": "12:00",
                    "cancel": "入住前24小时免费取消",
                },
            }
    return {"status": "not_found", "hotel_id": hotel_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8011)
