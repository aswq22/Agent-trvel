# mcp_servers/dianping.py
# 使用高德地图 POI API 提供真实景点和餐厅数据（高德 POI 类型覆盖大众点评全部核心场景）
# 高德 POI 类型代码: 110000=风景名胜, 050000=餐饮服务
# API 文档: https://lbs.amap.com/api/webservice/guide/api/search
from typing import Optional
import httpx
from fastmcp import FastMCP
from app.config import config

mcp = FastMCP("Dianping")

GAODE_BASE = "https://restapi.amap.com"

# 高德 POI 类型映射
_ATTRACTION_TYPES = "110000"   # 风景名胜（景区、公园、博物馆等）
_RESTAURANT_TYPES = "050000"   # 餐饮服务（餐厅、小吃、咖啡厅等）

# 标签关键词 → 高德 POI 子类型映射（用于 tags 筛选）
_TAG_TYPE_MAP = {
    "历史文化": "110100",   # 旅游景点
    "自然": "110200",        # 自然地物
    "亲子": "110000",        # 风景名胜（含动物园等）
    "购物": "060000",        # 购物服务
    "火锅": "050100",        # 中餐厅
    "川菜": "050100",
}

# 菜系 → 高德关键词映射
_CUISINE_KEYWORD_MAP = {
    "火锅": "火锅",
    "川菜": "川菜",
    "小吃": "小吃",
    "烧烤": "烧烤",
    "日料": "日料",
    "西餐": "西餐",
}

# 无 API Key 时的 Mock 降级数据（仅成都）
_MOCK_ATTRACTIONS = [
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
]

_MOCK_RESTAURANTS = [
    {"id": "REST001", "name": "大龙燚火锅（春熙路店）", "rating": 4.8, "review_count": 23450,
     "cuisine": "火锅", "avg_price_per_person": 120.0,
     "address": "锦江区红星路三段1号IFS国际金融中心B2层", "lat": 30.6570, "lng": 104.0831,
     "open_hours": "10:30-02:00", "signature_dishes": ["鸳鸯锅", "毛肚", "鲜毛血旺"]},
    {"id": "REST002", "name": "钟水饺（总府路店）", "rating": 4.7, "review_count": 15670,
     "cuisine": "川菜小吃", "avg_price_per_person": 30.0,
     "address": "青羊区总府路21号", "lat": 30.6598, "lng": 104.0778,
     "open_hours": "08:00-21:00", "signature_dishes": ["钟水饺", "赖汤圆", "担担面"]},
    {"id": "REST003", "name": "陈麻婆豆腐（总店）", "rating": 4.8, "review_count": 31200,
     "cuisine": "川菜", "avg_price_per_person": 60.0,
     "address": "金牛区西玉龙街197号", "lat": 30.6720, "lng": 104.0550,
     "open_hours": "10:30-21:00", "signature_dishes": ["麻婆豆腐", "夫妻肺片", "回锅肉"]},
    {"id": "REST004", "name": "蜀九香火锅（宽窄店）", "rating": 4.7, "review_count": 18920,
     "cuisine": "火锅", "avg_price_per_person": 100.0,
     "address": "青羊区宽巷子附近", "lat": 30.6670, "lng": 104.0500,
     "open_hours": "11:00-01:00", "signature_dishes": ["麻辣牛肉", "脑花", "鸭血"]},
    {"id": "REST005", "name": "龙抄手（春熙路总店）", "rating": 4.6, "review_count": 22100,
     "cuisine": "川菜小吃", "avg_price_per_person": 40.0,
     "address": "锦江区春熙路南一段20号", "lat": 30.6590, "lng": 104.0810,
     "open_hours": "09:00-22:00", "signature_dishes": ["龙抄手", "红油抄手", "清汤抄手"]},
]


def _parse_location(location_str: str) -> tuple[float, float]:
    """Parse Gaode location string 'lng,lat' → (lat, lng)."""
    try:
        lng, lat = location_str.split(",")
        return float(lat), float(lng)
    except Exception:
        return 0.0, 0.0


def _gaode_poi_to_attraction(poi: dict, idx: int) -> dict:
    lat, lng = _parse_location(poi.get("location", "0,0"))
    rating_raw = poi.get("biz_ext", {}).get("rating", "") or poi.get("rating", "")
    try:
        rating = float(rating_raw)
    except (ValueError, TypeError):
        rating = 4.5
    return {
        "id": f"GA{idx:04d}",
        "name": poi.get("name", ""),
        "rating": rating,
        "review_count": 0,
        "ticket_price": 0.0,
        "address": poi.get("address", ""),
        "lat": lat,
        "lng": lng,
        "tags": [t for t in poi.get("type", "").split(";") if t],
        "open_hours": poi.get("biz_ext", {}).get("open_time", "请查询官网"),
        "highlights": poi.get("name", ""),
        "tel": poi.get("tel", ""),
    }


def _gaode_poi_to_restaurant(poi: dict, idx: int) -> dict:
    lat, lng = _parse_location(poi.get("location", "0,0"))
    biz = poi.get("biz_ext", {}) or {}
    rating_raw = biz.get("rating", "") or poi.get("rating", "")
    cost_raw = biz.get("cost", "") or "0"
    try:
        rating = float(rating_raw)
    except (ValueError, TypeError):
        rating = 4.0
    try:
        avg_price = float(cost_raw)
    except (ValueError, TypeError):
        avg_price = 0.0
    cuisine = poi.get("type", "").split(";")[1] if ";" in poi.get("type", "") else "餐饮"
    return {
        "id": f"GR{idx:04d}",
        "name": poi.get("name", ""),
        "rating": rating,
        "review_count": 0,
        "cuisine": cuisine,
        "avg_price_per_person": avg_price,
        "address": poi.get("address", ""),
        "lat": lat,
        "lng": lng,
        "open_hours": biz.get("open_time", "请查询官网"),
        "signature_dishes": [],
        "tel": poi.get("tel", ""),
    }


async def _gaode_search(keywords: str, city: str, types: str, offset: int = 20) -> list[dict]:
    """Call Gaode Places API and return raw POI list."""
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.get(
            f"{GAODE_BASE}/v3/place/text",
            params={
                "keywords": keywords,
                "city": city,
                "types": types,
                "key": config.gaode_api_key,
                "output": "json",
                "offset": offset,
                "extensions": "all",
            },
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("status") == "1":
            return data.get("pois", [])
        return []


@mcp.tool()
async def dianping_attraction_search(
    city: str,
    keywords: str = "",
    tags: Optional[str] = None,
    max_ticket_price: Optional[float] = None,
) -> dict:
    """搜索景点（优先调用高德真实数据，无 API Key 时降级为 Mock 数据）

    Args:
        city: 城市名，如 "成都"、"北京"、"上海"
        keywords: 景点关键词，为空则搜索全部热门景点
        tags: 标签筛选，如 "历史文化,亲子"（逗号分隔），为空不限
        max_ticket_price: 最高票价（元），为空不限

    Returns:
        景点列表，含名称、地址、评分、经纬度、标签、开放时间
    """
    # 有 API Key → 调用高德真实数据
    if config.gaode_api_key:
        try:
            search_kw = keywords or f"{city}景点"
            # 有 tags 时尝试映射到更精确的 POI 类型
            poi_type = _ATTRACTION_TYPES
            if tags:
                for tag in tags.split(","):
                    tag = tag.strip()
                    if tag in _TAG_TYPE_MAP:
                        poi_type = _TAG_TYPE_MAP[tag]
                        break

            pois = await _gaode_search(search_kw, city, poi_type)
            attractions = [_gaode_poi_to_attraction(p, i) for i, p in enumerate(pois)]

            if max_ticket_price is not None:
                attractions = [a for a in attractions if a["ticket_price"] <= max_ticket_price]

            return {
                "status": "success",
                "source": "gaode_realtime",
                "city": city,
                "total": len(attractions),
                "attractions": attractions,
            }
        except Exception as e:
            # API 调用失败时降级到 Mock
            pass

    # 无 API Key 或调用失败 → Mock 数据（仅成都）
    attractions = list(_MOCK_ATTRACTIONS)
    if keywords:
        attractions = [a for a in attractions
                       if keywords in a["name"] or keywords in a.get("highlights", "")]
    if tags:
        tag_list = [t.strip() for t in tags.split(",")]
        attractions = [a for a in attractions
                       if any(t in a.get("tags", []) for t in tag_list)]
    if max_ticket_price is not None:
        attractions = [a for a in attractions if a["ticket_price"] <= max_ticket_price]
    attractions.sort(key=lambda x: x["rating"], reverse=True)

    return {
        "status": "success",
        "source": "mock",
        "city": city,
        "total": len(attractions),
        "attractions": attractions,
    }


@mcp.tool()
async def dianping_restaurant_search(
    city: str,
    area: str = "",
    cuisine: str = "",
    max_price_per_person: Optional[float] = None,
) -> dict:
    """搜索餐厅（优先调用高德真实数据，无 API Key 时降级为 Mock 数据）

    Args:
        city: 城市名，如 "成都"、"北京"、"上海"
        area: 区域，如 "锦江区"，为空表示全市
        cuisine: 菜系，如 "火锅"、"川菜"、"烧烤"，为空不限
        max_price_per_person: 人均最高价格（元），为空不限

    Returns:
        餐厅列表，含名称、地址、评分、人均消费、菜系、经纬度
    """
    if config.gaode_api_key:
        try:
            # 菜系关键词映射
            kw = _CUISINE_KEYWORD_MAP.get(cuisine, cuisine) if cuisine else "餐厅美食"
            search_city = f"{area}{city}" if area else city

            pois = await _gaode_search(kw, search_city, _RESTAURANT_TYPES)
            restaurants = [_gaode_poi_to_restaurant(p, i) for i, p in enumerate(pois)]

            if max_price_per_person is not None:
                restaurants = [r for r in restaurants
                               if r["avg_price_per_person"] == 0
                               or r["avg_price_per_person"] <= max_price_per_person]

            return {
                "status": "success",
                "source": "gaode_realtime",
                "city": city,
                "total": len(restaurants),
                "restaurants": restaurants,
            }
        except Exception:
            pass

    # Mock 降级
    restaurants = list(_MOCK_RESTAURANTS)
    if area:
        restaurants = [r for r in restaurants if area in r.get("address", "")]
    if cuisine:
        restaurants = [r for r in restaurants if cuisine in r.get("cuisine", "")]
    if max_price_per_person is not None:
        restaurants = [r for r in restaurants
                       if r["avg_price_per_person"] <= max_price_per_person]
    restaurants.sort(key=lambda x: x["rating"], reverse=True)

    return {
        "status": "success",
        "source": "mock",
        "city": city,
        "total": len(restaurants),
        "restaurants": restaurants,
    }


@mcp.tool()
async def dianping_menu(restaurant_id: str) -> dict:
    """获取餐厅招牌菜（Mock 数据，真实菜单建议通过餐厅官网或点餐平台获取）

    Args:
        restaurant_id: 餐厅 ID

    Returns:
        餐厅详情和招牌菜列表
    """
    for r in _MOCK_RESTAURANTS:
        if r["id"] == restaurant_id:
            return {
                "status": "success",
                "restaurant": r,
                "signature_dishes": r.get("signature_dishes", []),
                "must_try": r.get("signature_dishes", [])[0] if r.get("signature_dishes") else "",
            }
    return {"status": "not_found", "restaurant_id": restaurant_id,
            "note": "高德实时数据餐厅请通过餐厅电话或官方平台查询菜单"}


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8012)
