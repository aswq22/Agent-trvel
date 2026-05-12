# mcp_servers/ctrip.py
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("Ctrip")

# Mock data (replace with real Ctrip API when key is available)
_mock_hotels_db: dict[str, list[dict]] = {
    "成都": [
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
    ],
    "Chengdu": [
        {
            "hotel_id": "CD001EN",
            "name": "Shangri-La Chengdu",
            "stars": 5,
            "rating": 4.9,
            "price_per_night": 180.0,
            "address": "9 Binjiang East Road, Jinjiang District",
            "lat": 30.5728,
            "lng": 104.0668,
            "district": "Jinjiang",
            "amenities": ["Free WiFi", "Pool", "Gym", "Parking", "Executive Lounge"],
        },
    ],
}


@mcp.tool()
async def ctrip_hotel_search(
    city: str,
    check_in: str,
    check_out: str,
    max_price_per_night: Optional[float] = None,
    min_stars: Optional[int] = None,
    district: Optional[str] = None,
) -> dict:
    """搜索携程酒店列表

    Args:
        city: 城市名，如 "成都" 或 "Chengdu"
        check_in: 入住日期，格式 YYYY-MM-DD
        check_out: 退房日期，格式 YYYY-MM-DD
        max_price_per_night: 每晚最高价格（元），为空表示不限
        min_stars: 最低星级（1-5），为空表示不限
        district: 区域筛选，如 "锦江区"，为空表示不限

    Returns:
        符合条件的酒店列表
    """
    hotels = list(_mock_hotels_db.get(city, _mock_hotels_db.get("成都", [])))

    if max_price_per_night is not None:
        hotels = [h for h in hotels if h["price_per_night"] <= max_price_per_night]
    if min_stars is not None:
        hotels = [h for h in hotels if h["stars"] >= min_stars]
    if district:
        hotels = [h for h in hotels if district in h.get("district", "")]

    return {
        "status": "success",
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
    for hotels in _mock_hotels_db.values():
        for h in hotels:
            if h["hotel_id"] == hotel_id:
                return {
                    "status": "success",
                    "hotel": h,
                    "room_types": [
                        {"type": "标准双人间", "bed": "两张单床", "area": "28㎡", "price": h["price_per_night"]},
                        {"type": "豪华大床房", "bed": "一张大床", "area": "36㎡", "price": h["price_per_night"] * 1.3},
                    ],
                    "policies": {"check_in": "14:00", "check_out": "12:00", "cancel": "入住前24小时免费取消"},
                }
    return {"status": "not_found", "hotel_id": hotel_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8011)
