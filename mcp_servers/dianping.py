# mcp_servers/dianping.py
from typing import Optional
from fastmcp import FastMCP

mcp = FastMCP("Dianping")

_mock_attractions: dict[str, list[dict]] = {
    "成都": [
        {"id": "ATT001", "name": "成都大熊猫繁育研究基地", "rating": 4.9, "review_count": 45230,
         "ticket_price": 58.0, "address": "成华区熊猫大道1375号", "lat": 30.7376, "lng": 104.1393,
         "tags": ["自然", "亲子", "热门"], "open_hours": "07:30-18:00",
         "highlights": "全球最大圈养大熊猫种群，可近距离观看大熊猫"},
        {"id": "ATT002", "name": "宽窄巷子", "rating": 4.7, "review_count": 68120,
         "ticket_price": 0.0, "address": "青羊区宽巷子", "lat": 30.6665, "lng": 104.0490,
         "tags": ["历史文化", "美食", "购物", "热门"], "open_hours": "全天",
         "highlights": "清代古街，成都最具代表性的历史文化街区"},
        {"id": "ATT003", "name": "武侯祠", "rating": 4.8, "review_count": 32456,
         "ticket_price": 50.0, "address": "武侯区武侯祠大街231号", "lat": 30.6410, "lng": 104.0470,
         "tags": ["历史文化", "三国文化"], "open_hours": "08:00-18:00",
         "highlights": "全国唯一君臣合祀祠庙，三国文化圣地"},
        {"id": "ATT004", "name": "锦里古街", "rating": 4.6, "review_count": 52340,
         "ticket_price": 0.0, "address": "武侯区武侯祠大街231号附近", "lat": 30.6400, "lng": 104.0490,
         "tags": ["美食", "购物", "历史文化"], "open_hours": "全天",
         "highlights": "西蜀第一街，紧邻武侯祠，成都小吃集中地"},
        {"id": "ATT005", "name": "都江堰", "rating": 4.9, "review_count": 28900,
         "ticket_price": 80.0, "address": "都江堰市景区路", "lat": 30.9994, "lng": 103.5900,
         "tags": ["世界遗产", "自然", "历史文化"], "open_hours": "08:00-17:30",
         "highlights": "两千年水利工程，世界文化遗产"},
    ],
}

_mock_restaurants: dict[str, list[dict]] = {
    "成都": [
        {"id": "REST001", "name": "大龙燚火锅（春熙路店）", "rating": 4.8, "review_count": 23450,
         "cuisine": "火锅", "avg_price_per_person": 120.0,
         "address": "锦江区红星路三段1号IFS国际金融中心B2层", "lat": 30.6570, "lng": 104.0831,
         "open_hours": "10:30-02:00", "signature_dishes": ["鸳鸯锅", "毛肚", "鲜毛血旺"]},
        {"id": "REST002", "name": "钟水饺（总府路店）", "rating": 4.7, "review_count": 15670,
         "cuisine": "川菜小吃", "avg_price_per_person": 30.0,
         "address": "青羊区总府路21号", "lat": 30.6598, "lng": 104.0778,
         "open_hours": "08:00-21:00", "signature_dishes": ["钟水饺", "赖汤圆", "担担面"]},
        {"id": "REST003", "name": "蜀九香火锅（宽窄店）", "rating": 4.7, "review_count": 18920,
         "cuisine": "火锅", "avg_price_per_person": 100.0,
         "address": "青羊区宽巷子附近", "lat": 30.6670, "lng": 104.0500,
         "open_hours": "11:00-01:00", "signature_dishes": ["麻辣牛肉", "脑花", "鸭血"]},
        {"id": "REST004", "name": "陈麻婆豆腐（总店）", "rating": 4.8, "review_count": 31200,
         "cuisine": "川菜", "avg_price_per_person": 60.0,
         "address": "金牛区西玉龙街197号", "lat": 30.6720, "lng": 104.0550,
         "open_hours": "10:30-21:00", "signature_dishes": ["麻婆豆腐", "夫妻肺片", "回锅肉"]},
        {"id": "REST005", "name": "龙抄手（春熙路总店）", "rating": 4.6, "review_count": 22100,
         "cuisine": "川菜小吃", "avg_price_per_person": 40.0,
         "address": "锦江区春熙路南一段20号", "lat": 30.6590, "lng": 104.0810,
         "open_hours": "09:00-22:00", "signature_dishes": ["龙抄手", "红油抄手", "清汤抄手"]},
    ],
}


@mcp.tool()
async def dianping_attraction_search(
    city: str,
    keywords: str = "",
    tags: Optional[str] = None,
    max_ticket_price: Optional[float] = None,
) -> dict:
    """搜索大众点评景点

    Args:
        city: 城市名，如 "成都"
        keywords: 搜索关键词，为空返回所有景点
        tags: 标签筛选，如 "历史文化" 或 "亲子"，为空表示不限
        max_ticket_price: 最高票价（元），为空表示不限（含免费）

    Returns:
        符合条件的景点列表，按评分降序
    """
    attractions = list(_mock_attractions.get(city, []))

    if keywords:
        attractions = [a for a in attractions if keywords in a["name"] or keywords in a.get("highlights", "")]
    if tags:
        attractions = [a for a in attractions if any(t in a.get("tags", []) for t in tags.split(","))]
    if max_ticket_price is not None:
        attractions = [a for a in attractions if a["ticket_price"] <= max_ticket_price]

    attractions.sort(key=lambda x: x["rating"], reverse=True)
    return {"status": "success", "city": city, "total": len(attractions), "attractions": attractions}


@mcp.tool()
async def dianping_restaurant_search(
    city: str,
    area: str = "",
    cuisine: str = "",
    max_price_per_person: Optional[float] = None,
) -> dict:
    """搜索大众点评餐厅

    Args:
        city: 城市名，如 "成都"
        area: 区域，如 "锦江区"，为空表示全市
        cuisine: 菜系，如 "火锅" 或 "川菜"，为空表示不限
        max_price_per_person: 人均最高价格（元），为空表示不限

    Returns:
        符合条件的餐厅列表，按评分降序
    """
    restaurants = list(_mock_restaurants.get(city, []))

    if area:
        restaurants = [r for r in restaurants if area in r.get("address", "")]
    if cuisine:
        restaurants = [r for r in restaurants if cuisine in r.get("cuisine", "")]
    if max_price_per_person is not None:
        restaurants = [r for r in restaurants if r["avg_price_per_person"] <= max_price_per_person]

    restaurants.sort(key=lambda x: x["rating"], reverse=True)
    return {"status": "success", "city": city, "total": len(restaurants), "restaurants": restaurants}


@mcp.tool()
async def dianping_menu(restaurant_id: str) -> dict:
    """获取餐厅招牌菜单

    Args:
        restaurant_id: 餐厅 ID（从 dianping_restaurant_search 返回）

    Returns:
        餐厅详情和招牌菜
    """
    for restaurants in _mock_restaurants.values():
        for r in restaurants:
            if r["id"] == restaurant_id:
                return {
                    "status": "success",
                    "restaurant": r,
                    "signature_dishes": r.get("signature_dishes", []),
                    "must_try": r.get("signature_dishes", [])[0] if r.get("signature_dishes") else "",
                }
    return {"status": "not_found", "restaurant_id": restaurant_id}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8012)
