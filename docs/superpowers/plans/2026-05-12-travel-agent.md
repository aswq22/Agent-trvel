# 旅游多智能体系统 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将现有 AIOps 系统重构为旅游多智能体规划系统，支持景点/路线/酒店/美食推荐并生成完整中英文攻略。

**Architecture:** 三阶段分阶段混合执行：ParserAgent（解析输入）→ AttractionAgent（串行）→ RouteAgent/HotelAgent/FoodAgent（LangGraph Send() 并行）→ StrategyAgent（汇总，SSE 流式）。每个 Agent 是独立模块中的异步函数，通过 MCP 工具调用外部 API，失败时 retry 2 次后降级到 LLM 内置知识。

**Tech Stack:** FastAPI, LangGraph (langgraph>=0.0.40), Qwen via langchain_qwq, MCP via FastMCP + langchain_mcp_adapters, Gaode Maps REST API, Ctrip/Dianping (Mock with real-API structure), SSE via sse-starlette

---

## File Map

| 文件 | 操作 | 职责 |
|------|------|------|
| `app/agent/travel/__init__.py` | 新建 | 导出 |
| `app/agent/travel/state.py` | 新建 | TripParams, TravelPlanState, merge_dicts |
| `app/agent/travel/mcp_utils.py` | 新建 | get_travel_mcp_client（2次重试，按服务分组） |
| `app/agent/travel/parser.py` | 新建 | ParserAgent 节点 |
| `app/agent/travel/attraction.py` | 新建 | AttractionAgent 节点（Gaode + Dianping） |
| `app/agent/travel/route.py` | 新建 | RouteAgent 节点（Gaode 路线规划） |
| `app/agent/travel/hotel.py` | 新建 | HotelAgent 节点（Ctrip） |
| `app/agent/travel/food.py` | 新建 | FoodAgent 节点（Dianping） |
| `app/agent/travel/strategy.py` | 新建 | StrategyAgent 节点（综合输出，双语） |
| `app/agent/travel/graph.py` | 新建 | 主编排图（StateGraph + Send() 并行） |
| `app/models/travel.py` | 新建 | TripRequest, SSE 事件 Pydantic 模型 |
| `app/services/travel_service.py` | 新建 | TravelService（包装图，流式事件生成器） |
| `app/api/travel.py` | 新建 | POST /api/travel/plan（SSE） |
| `mcp_servers/gaode_maps.py` | 新建 | 高德地图 MCP Server（POI/路线/距离矩阵） |
| `mcp_servers/ctrip.py` | 新建 | 携程酒店 MCP Server（Mock + 真实 API 接口） |
| `mcp_servers/dianping.py` | 新建 | 大众点评 MCP Server（Mock + 真实 API 接口） |
| `app/config.py` | 修改 | 添加 gaode_api_key、travel MCP URLs |
| `app/main.py` | 修改 | 注册 travel 路由，移除 aiops 路由 |
| `tests/agent/travel/test_state.py` | 新建 | TripParams 验证测试 |
| `tests/agent/travel/test_parser.py` | 新建 | ParserAgent 单元测试（mock LLM） |
| `tests/agent/travel/test_agents.py` | 新建 | 各 Agent 节点测试（mock MCP + LLM） |
| `tests/api/test_travel.py` | 新建 | Travel API 端到端测试 |

---

## Task 1: State & Data Models

**Files:**
- Create: `app/agent/travel/state.py`
- Create: `app/agent/travel/__init__.py`
- Create: `tests/agent/travel/__init__.py`
- Create: `tests/agent/__init__.py`
- Create: `tests/agent/travel/test_state.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/travel/test_state.py
import pytest
from pydantic import ValidationError
from app.agent.travel.state import TripParams, TravelPlanState, merge_dicts


def test_trip_params_defaults():
    p = TripParams(destination="成都", budget=3000.0)
    assert p.days == 3
    assert p.num_people == 2
    assert p.language == "zh"
    assert p.preferences == []


def test_trip_params_requires_destination():
    with pytest.raises(ValidationError):
        TripParams(budget=3000.0)  # destination is required


def test_trip_params_english():
    p = TripParams(destination="Chengdu", budget=500.0, language="en")
    assert p.language == "en"


def test_merge_dicts():
    a = {"parser": "err1"}
    b = {"attraction": "err2"}
    result = merge_dicts(a, b)
    assert result == {"parser": "err1", "attraction": "err2"}


def test_merge_dicts_overwrite():
    a = {"key": "old"}
    b = {"key": "new"}
    assert merge_dicts(a, b) == {"key": "new"}


def test_travel_plan_state_typing():
    from app.agent.travel.state import TravelPlanState
    # TypedDict - just verify it can be used as a dict
    state: TravelPlanState = {
        "user_input": "test",
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }
    assert state["user_input"] == "test"
```

- [ ] **Step 2: 运行测试，确认失败**

```
pytest tests/agent/travel/test_state.py -v
```
预期：`ModuleNotFoundError: No module named 'app.agent.travel'`

- [ ] **Step 3: 创建 `__init__.py` 文件**

```python
# app/agent/travel/__init__.py
# (empty)
```

```python
# tests/agent/__init__.py
# (empty)
```

```python
# tests/agent/travel/__init__.py
# (empty)
```

- [ ] **Step 4: 实现 `app/agent/travel/state.py`**

```python
# app/agent/travel/state.py
from typing import List, TypedDict, Annotated, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class TripParams(BaseModel):
    destination: str = Field(description="目的地城市，如'成都'")
    start_date: str = Field(default="", description="出发日期，格式 YYYY-MM-DD")
    days: int = Field(default=3, description="出行天数")
    num_people: int = Field(default=2, description="出行人数")
    budget: float = Field(default=3000.0, description="总预算（元）")
    preferences: List[str] = Field(default_factory=list, description="偏好标签")
    language: str = Field(default="zh", description="输出语言: zh 或 en")


def merge_dicts(existing: dict, new: dict) -> dict:
    return {**existing, **new}


class TravelPlanState(TypedDict):
    user_input: str
    trip_params: Optional[TripParams]
    attractions: List[dict]
    route: dict
    hotels: List[dict]
    foods: List[dict]
    final_plan: str
    errors: Annotated[dict, merge_dicts]
    messages: Annotated[List[BaseMessage], add_messages]
```

- [ ] **Step 5: 运行测试，确认通过**

```
pytest tests/agent/travel/test_state.py -v
```
预期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/agent/travel/__init__.py app/agent/travel/state.py tests/agent/__init__.py tests/agent/travel/__init__.py tests/agent/travel/test_state.py
git commit -m "feat: add travel agent state models (TripParams, TravelPlanState)"
```

---

## Task 2: Config & MCP Utils

**Files:**
- Modify: `app/config.py`
- Create: `app/agent/travel/mcp_utils.py`

- [ ] **Step 1: 写失败测试**

```python
# 追加到 tests/agent/travel/test_state.py 末尾
def test_travel_mcp_servers_config():
    from app.config import config
    servers = config.travel_mcp_servers
    assert "gaode" in servers
    assert "ctrip" in servers
    assert "dianping" in servers
    for s in servers.values():
        assert "transport" in s
        assert "url" in s
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_state.py::test_travel_mcp_servers_config -v
```
预期：`AttributeError: 'Settings' object has no attribute 'travel_mcp_servers'`

- [ ] **Step 3: 修改 `app/config.py`（在现有 Settings 类中添加）**

在 `mcp_monitor_url` 字段后，`mcp_servers` property 前，添加：

```python
    # Gaode Maps API
    gaode_api_key: str = ""

    # Travel MCP server URLs
    mcp_gaode_url: str = "http://localhost:8010/mcp"
    mcp_ctrip_url: str = "http://localhost:8011/mcp"
    mcp_dianping_url: str = "http://localhost:8012/mcp"
```

在 `mcp_servers` property 后，添加新 property：

```python
    @property
    def travel_mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        return {
            "gaode": {"transport": "streamable-http", "url": self.mcp_gaode_url},
            "ctrip": {"transport": "streamable-http", "url": self.mcp_ctrip_url},
            "dianping": {"transport": "streamable-http", "url": self.mcp_dianping_url},
        }
```

- [ ] **Step 4: 创建 `app/agent/travel/mcp_utils.py`**

```python
# app/agent/travel/mcp_utils.py
import functools
from typing import List, Optional
from langchain_mcp_adapters.client import MultiServerMCPClient

from app.agent.mcp_client import retry_interceptor, get_mcp_client
from app.config import config

# retry 2 次（spec 要求）
_travel_retry = functools.partial(retry_interceptor, max_retries=2)


async def get_travel_mcp_client(
    server_names: Optional[List[str]] = None,
) -> MultiServerMCPClient:
    """获取旅游专用 MCP 客户端（2次重试，每次创建新实例）"""
    all_servers = config.travel_mcp_servers
    if server_names:
        servers = {k: v for k, v in all_servers.items() if k in server_names}
    else:
        servers = all_servers
    return await get_mcp_client(
        servers=servers,
        tool_interceptors=[_travel_retry],
        force_new=True,
    )
```

- [ ] **Step 5: 运行测试，确认通过**

```
pytest tests/agent/travel/test_state.py -v
```
预期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/config.py app/agent/travel/mcp_utils.py
git commit -m "feat: add travel API config fields and MCP client helper"
```

---

## Task 3: Gaode Maps MCP Server

**Files:**
- Create: `mcp_servers/gaode_maps.py`

> **注意：** 高德地图 API Key 需在 https://lbs.amap.com 注册获取，免费额度：每日 30 万次。将 Key 设置到 `.env` 的 `GAODE_API_KEY`。

- [ ] **Step 1: 创建 `mcp_servers/gaode_maps.py`**

```python
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
```

- [ ] **Step 2: 手动验证 MCP Server 能启动**

```bash
python mcp_servers/gaode_maps.py
```
预期：服务启动在 http://0.0.0.0:8010，没有错误（API key 为空时工具调用会失败但服务本身能启动）

- [ ] **Step 3: Commit**

```bash
git add mcp_servers/gaode_maps.py
git commit -m "feat: add Gaode Maps MCP server (POI search, route plan, distance matrix)"
```

---

## Task 4: Ctrip MCP Server

**Files:**
- Create: `mcp_servers/ctrip.py`

> **注意：** 携程 Open API 需企业资质。此实现使用结构化 Mock 数据，接口签名与真实 API 一致，获取真实 key 后替换 `_fetch_real_hotels` 函数体即可。

- [ ] **Step 1: 创建 `mcp_servers/ctrip.py`**

```python
# mcp_servers/ctrip.py
from typing import Optional
from fastmcp import FastMCP
from app.config import config

mcp = FastMCP("Ctrip")

# Mock 数据（获取真实 Ctrip API key 后替换 _mock_hotels_db 为真实 API 调用）
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
    # Find hotel across all cities
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
```

- [ ] **Step 2: 手动验证 MCP Server 能启动**

```bash
python mcp_servers/ctrip.py
```
预期：服务启动在 http://0.0.0.0:8011，没有错误

- [ ] **Step 3: Commit**

```bash
git add mcp_servers/ctrip.py
git commit -m "feat: add Ctrip hotel MCP server (mock data, real-API-compatible interface)"
```

---

## Task 5: Dianping MCP Server

**Files:**
- Create: `mcp_servers/dianping.py`

- [ ] **Step 1: 创建 `mcp_servers/dianping.py`**

```python
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
```

- [ ] **Step 2: 手动验证 MCP Server 能启动**

```bash
python mcp_servers/dianping.py
```
预期：服务启动在 http://0.0.0.0:8012，没有错误

- [ ] **Step 3: Commit**

```bash
git add mcp_servers/dianping.py
git commit -m "feat: add Dianping MCP server (attractions + restaurants + menu)"
```

---

## Task 6: ParserAgent

**Files:**
- Create: `app/agent/travel/parser.py`
- Create: `tests/agent/travel/test_parser.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/travel/test_parser.py
import pytest
from unittest.mock import AsyncMock, patch
from app.agent.travel.state import TravelPlanState, TripParams
from app.agent.travel.parser import parser_node


def _make_state(user_input: str) -> TravelPlanState:
    return {
        "user_input": user_input,
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }


@pytest.mark.asyncio
async def test_parser_returns_trip_params():
    mock_params = TripParams(destination="成都", days=5, budget=5000.0, preferences=["美食", "历史"])
    # _invoke_parser_chain 是 parser.py 中提取的内部帮助函数，直接 mock 它最简洁
    with patch("app.agent.travel.parser._invoke_parser_chain", new=AsyncMock(return_value=mock_params)):
        state = _make_state("帮我规划5天成都之旅，预算5000元，喜欢美食和历史")
        result = await parser_node(state)

    assert "trip_params" in result
    assert result["trip_params"].destination == "成都"


@pytest.mark.asyncio
async def test_parser_fallback_on_error():
    with patch("app.agent.travel.parser._invoke_parser_chain",
               new=AsyncMock(side_effect=Exception("LLM error"))):
        state = _make_state("garbage input")
        result = await parser_node(state)

    assert "trip_params" in result
    assert "parser" in result.get("errors", {})


@pytest.mark.asyncio
async def test_parser_detects_english():
    mock_params = TripParams(destination="Chengdu", days=4, budget=500.0, language="en")
    with patch("app.agent.travel.parser._invoke_parser_chain", new=AsyncMock(return_value=mock_params)):
        state = _make_state("Plan a 4-day trip to Chengdu, budget $500")
        result = await parser_node(state)

    assert result["trip_params"].language == "en"
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_parser.py -v
```
预期：`ModuleNotFoundError: No module named 'app.agent.travel.parser'`

- [ ] **Step 3: 实现 `app/agent/travel/parser.py`**

```python
# app/agent/travel/parser.py
from textwrap import dedent
from typing import Dict, Any

from langchain_core.prompts import ChatPromptTemplate
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState, TripParams

_SYSTEM = dedent("""
    你是旅行规划助手。从用户输入中提取旅行参数，填充到指定结构中。

    语言检测规则：
    - 输入主要是英文 → language 设为 "en"
    - 其他情况 → language 设为 "zh"

    无法确定的字段使用默认值：
    - start_date: ""（留空）
    - days: 3
    - num_people: 2
    - budget: 3000.0
    - preferences: []
""").strip()

_parser_prompt = ChatPromptTemplate.from_messages([
    ("system", _SYSTEM),
    ("human", "{user_input}"),
])


async def _invoke_parser_chain(user_input: str) -> TripParams:
    """构建并执行解析 chain，单独提取以便测试 mock。"""
    llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
    chain = _parser_prompt | llm.with_structured_output(TripParams)
    return await chain.ainvoke({"user_input": user_input})


async def parser_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== ParserAgent：解析旅行参数 ===")
    try:
        params = await _invoke_parser_chain(state["user_input"])
        logger.info(f"解析结果: destination={params.destination}, days={params.days}, language={params.language}")
        return {"trip_params": params}
    except Exception as e:
        logger.error(f"ParserAgent 失败: {e}", exc_info=True)
        return {
            "trip_params": TripParams(destination="", start_date="", days=3, budget=3000.0),
            "errors": {"parser": str(e)},
        }
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/agent/travel/test_parser.py -v
```
预期：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/parser.py tests/agent/travel/test_parser.py
git commit -m "feat: add ParserAgent (LLM-based trip params extraction with language detection)"
```

---

## Task 7: AttractionAgent

**Files:**
- Create: `app/agent/travel/attraction.py`
- Create: `tests/agent/travel/test_agents.py`

- [ ] **Step 1: 写失败测试**

```python
# tests/agent/travel/test_agents.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from app.agent.travel.state import TravelPlanState, TripParams


def _make_full_state(destination="成都", days=3, language="zh") -> TravelPlanState:
    return {
        "user_input": "test",
        "trip_params": TripParams(destination=destination, days=days, budget=3000.0, language=language),
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }


@pytest.mark.asyncio
async def test_attraction_agent_returns_list():
    from app.agent.travel.attraction import attraction_node

    mock_tools = []
    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '[{"name": "大熊猫基地", "address": "成华区", "rating": 4.9, "reason": "必去"}]'

    with patch("app.agent.travel.attraction.get_travel_mcp_client") as mock_client_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=mock_tools)
        mock_client_fn.return_value = mock_client
        with patch("app.agent.travel.attraction.ChatQwen") as MockLLM:
            mock_llm_instance = MagicMock()
            mock_llm_instance.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm_instance

            result = await attraction_node(_make_full_state())

    assert "attractions" in result
    assert isinstance(result["attractions"], list)


@pytest.mark.asyncio
async def test_attraction_agent_graceful_on_mcp_error():
    from app.agent.travel.attraction import attraction_node

    with patch("app.agent.travel.attraction.get_travel_mcp_client", side_effect=Exception("MCP down")):
        result = await attraction_node(_make_full_state())

    assert "errors" in result
    assert "attraction" in result["errors"]
    assert result["attractions"] == []
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_agents.py::test_attraction_agent_returns_list -v
```
预期：`ModuleNotFoundError: No module named 'app.agent.travel.attraction'`

- [ ] **Step 3: 实现 `app/agent/travel/attraction.py`**

```python
# app/agent/travel/attraction.py
import json
import re
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client

_PROMPT = {
    "zh": dedent("""
        你是景点推荐专家。使用工具搜索{destination}的热门景点。

        旅行信息：
        - 目的地：{destination}
        - 天数：{days}天
        - 偏好：{preferences}

        步骤：
        1. 用 gaode_poi_search 搜索 "{destination} 景点"
        2. 用 dianping_attraction_search 搜索 {destination} 景点
        3. 综合两个来源，推荐最适合 {days} 天行程的 {num} 个景点

        最终以 JSON 数组格式输出景点，每项包含：name、address、rating、ticket_price、highlights、reason。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are an attractions expert. Use tools to find top attractions in {destination}.

        Trip info:
        - Destination: {destination}
        - Duration: {days} days
        - Preferences: {preferences}

        Steps:
        1. Use gaode_poi_search to search "{destination} attractions"
        2. Use dianping_attraction_search to search attractions in {destination}
        3. Recommend the best {num} attractions for a {days}-day trip

        Output as a JSON array only. Each item: name, address, rating, ticket_price, highlights, reason.
    """).strip(),
}


async def _run_react_loop(
    messages: List[BaseMessage],
    llm_with_tools,
    tool_map: dict,
    max_turns: int = 5,
) -> str:
    """通用 ReAct 循环：LLM → 工具调用 → LLM → ... → 最终文本"""
    for _ in range(max_turns):
        response = await llm_with_tools.ainvoke(messages)
        messages.append(response)

        if not (hasattr(response, "tool_calls") and response.tool_calls):
            return response.content if hasattr(response, "content") else str(response)

        for tc in response.tool_calls:
            tool = tool_map.get(tc["name"])
            if tool:
                try:
                    result = await tool.ainvoke(tc["args"])
                except Exception as e:
                    result = f"ERROR: {e}"
                messages.append(
                    ToolMessage(content=str(result), tool_call_id=tc["id"], name=tc["name"])
                )

    return messages[-1].content if hasattr(messages[-1], "content") else ""


def _parse_json_list(text: str) -> List[dict]:
    match = re.search(r"\[.*?\]", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return [{"raw": text}]


async def attraction_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== AttractionAgent：搜索景点 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    preferences = ", ".join(trip.preferences) if trip and trip.preferences else ("无特定偏好" if lang == "zh" else "none")
    num = min(days * 2, 8)

    try:
        mcp_client = await get_travel_mcp_client(["gaode", "dianping"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(destination=destination, days=days, preferences=preferences, num=num)
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]

        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        attractions = _parse_json_list(final_text)
        logger.info(f"AttractionAgent 完成，推荐 {len(attractions)} 个景点")
        return {"attractions": attractions}

    except Exception as e:
        logger.error(f"AttractionAgent 失败: {e}", exc_info=True)
        return {"attractions": [], "errors": {"attraction": str(e)}}
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/agent/travel/test_agents.py::test_attraction_agent_returns_list tests/agent/travel/test_agents.py::test_attraction_agent_graceful_on_mcp_error -v
```
预期：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/attraction.py tests/agent/travel/test_agents.py
git commit -m "feat: add AttractionAgent (ReAct loop with Gaode + Dianping tools)"
```

---

## Task 8: RouteAgent

**Files:**
- Create: `app/agent/travel/route.py`

- [ ] **Step 1: 为 RouteAgent 追加测试到 `tests/agent/travel/test_agents.py`**

```python
@pytest.mark.asyncio
async def test_route_agent_returns_dict():
    from app.agent.travel.route import route_node

    state = _make_full_state()
    state["attractions"] = [
        {"name": "大熊猫基地", "address": "成华区", "lat": 30.7376, "lng": 104.1393},
        {"name": "宽窄巷子", "address": "青羊区", "lat": 30.6665, "lng": 104.0490},
    ]

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '{"days": [{"day": 1, "attractions": ["大熊猫基地"], "transport": "地铁"}]}'

    with patch("app.agent.travel.route.get_travel_mcp_client") as mock_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        with patch("app.agent.travel.route.ChatQwen") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm

            result = await route_node(state)

    assert "route" in result
    assert isinstance(result["route"], dict)
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_agents.py::test_route_agent_returns_dict -v
```
预期：`ModuleNotFoundError: No module named 'app.agent.travel.route'`

- [ ] **Step 3: 实现 `app/agent/travel/route.py`**

```python
# app/agent/travel/route.py
import json
import re
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, ToolMessage, BaseMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client
from app.agent.travel.attraction import _run_react_loop

_PROMPT = {
    "zh": dedent("""
        你是路线规划专家。根据以下景点，规划{days}天的最优游览路线。

        目的地：{destination}
        天数：{days}天
        景点列表：
        {attractions_text}

        使用 gaode_distance_matrix 计算景点间距离，用 gaode_route_plan 获取路线详情。
        规划原则：
        - 地理位置相近的景点安排在同一天
        - 考虑景点开放时间和参观时长
        - 每天不超过 3 个主要景点

        以 JSON 格式输出，结构：
        {{
          "days": [
            {{"day": 1, "theme": "主题", "attractions": ["景点A", "景点B"], "transport": "交通方式", "tips": "当日提示"}},
            ...
          ],
          "total_distance_km": 数字
        }}
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a route planning expert. Plan the optimal {days}-day route for these attractions.

        Destination: {destination}
        Duration: {days} days
        Attractions:
        {attractions_text}

        Use gaode_distance_matrix for distances, gaode_route_plan for route details.
        Output as JSON:
        {{
          "days": [
            {{"day": 1, "theme": "theme", "attractions": ["A", "B"], "transport": "transport", "tips": "tip"}},
            ...
          ],
          "total_distance_km": number
        }}
        JSON only, no extra text.
    """).strip(),
}


def _parse_json_dict(text: str) -> dict:
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group())
        except json.JSONDecodeError:
            pass
    return {"raw": text}


async def route_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== RouteAgent：规划路线 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    attractions = state.get("attractions", [])

    attractions_text = "\n".join(
        f"- {a.get('name', 'Unknown')} ({a.get('address', '')})"
        for a in attractions
    ) or ("暂无景点数据" if lang == "zh" else "No attractions data")

    try:
        mcp_client = await get_travel_mcp_client(["gaode"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination, days=days, attractions_text=attractions_text
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        route = _parse_json_dict(final_text)
        logger.info(f"RouteAgent 完成，规划 {len(route.get('days', []))} 天行程")
        return {"route": route}

    except Exception as e:
        logger.error(f"RouteAgent 失败: {e}", exc_info=True)
        return {"route": {}, "errors": {"route": str(e)}}
```

- [ ] **Step 4: 运行测试，确认通过**

```
pytest tests/agent/travel/test_agents.py::test_route_agent_returns_dict -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/route.py
git commit -m "feat: add RouteAgent (Gaode route planning with ReAct loop)"
```

---

## Task 9: HotelAgent

**Files:**
- Create: `app/agent/travel/hotel.py`

- [ ] **Step 1: 追加测试**

```python
# 追加到 tests/agent/travel/test_agents.py
@pytest.mark.asyncio
async def test_hotel_agent_returns_list():
    from app.agent.travel.hotel import hotel_node

    state = _make_full_state()
    state["attractions"] = [{"name": "大熊猫基地", "address": "成华区锦官路"}]

    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '[{"name": "香格里拉酒店", "price_per_night": 1200, "rating": 4.9}]'

    with patch("app.agent.travel.hotel.get_travel_mcp_client") as mock_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        with patch("app.agent.travel.hotel.ChatQwen") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm

            result = await hotel_node(state)

    assert "hotels" in result
    assert isinstance(result["hotels"], list)
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_agents.py::test_hotel_agent_returns_list -v
```
预期：`ModuleNotFoundError: No module named 'app.agent.travel.hotel'`

- [ ] **Step 3: 实现 `app/agent/travel/hotel.py`**

```python
# app/agent/travel/hotel.py
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client
from app.agent.travel.attraction import _run_react_loop, _parse_json_list

_PROMPT = {
    "zh": dedent("""
        你是酒店推荐专家。为以下旅行安排合适的住宿。

        目的地：{destination}
        入住：{check_in}，退房：{check_out}（{days}晚）
        人均预算（住宿）：{hotel_budget:.0f}元/晚
        主要活动区域：{areas}

        使用 ctrip_hotel_search 搜索酒店，用 ctrip_hotel_detail 获取详情。
        推荐 3 个不同价位的酒店选项。

        以 JSON 数组格式输出，每项包含：name、stars、rating、price_per_night、address、amenities、reason。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a hotel expert. Find suitable accommodations for this trip.

        Destination: {destination}
        Check-in: {check_in}, Check-out: {check_out} ({days} nights)
        Hotel budget: {hotel_budget:.0f} CNY/night
        Activity areas: {areas}

        Use ctrip_hotel_search and ctrip_hotel_detail. Recommend 3 options at different price points.

        Output as JSON array: name, stars, rating, price_per_night, address, amenities, reason.
        JSON only.
    """).strip(),
}


async def hotel_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== HotelAgent：推荐酒店 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    budget = trip.budget if trip else 3000.0
    start_date = trip.start_date if trip else ""
    hotel_budget = (budget * 0.4) / days  # 40% of budget for accommodation

    # Determine areas from attractions
    attractions = state.get("attractions", [])
    areas = ", ".join({a.get("address", "").split("区")[0] + "区" for a in attractions[:3] if "区" in a.get("address", "")}) or destination

    try:
        mcp_client = await get_travel_mcp_client(["ctrip"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination,
            check_in=start_date or "待定",
            check_out="待定",
            days=days,
            hotel_budget=hotel_budget,
            areas=areas,
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        hotels = _parse_json_list(final_text)
        logger.info(f"HotelAgent 完成，推荐 {len(hotels)} 个酒店")
        return {"hotels": hotels}

    except Exception as e:
        logger.error(f"HotelAgent 失败: {e}", exc_info=True)
        return {"hotels": [], "errors": {"hotel": str(e)}}
```

- [ ] **Step 4: 运行测试**

```
pytest tests/agent/travel/test_agents.py::test_hotel_agent_returns_list -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/hotel.py
git commit -m "feat: add HotelAgent (Ctrip hotel search with budget-aware recommendations)"
```

---

## Task 10: FoodAgent

**Files:**
- Create: `app/agent/travel/food.py`

- [ ] **Step 1: 追加测试**

```python
# 追加到 tests/agent/travel/test_agents.py
@pytest.mark.asyncio
async def test_food_agent_returns_list():
    from app.agent.travel.food import food_node

    state = _make_full_state()
    mock_response = MagicMock()
    mock_response.tool_calls = []
    mock_response.content = '[{"name": "大龙燚火锅", "cuisine": "火锅", "avg_price": 120}]'

    with patch("app.agent.travel.food.get_travel_mcp_client") as mock_fn:
        mock_client = AsyncMock()
        mock_client.get_tools = AsyncMock(return_value=[])
        mock_fn.return_value = mock_client
        with patch("app.agent.travel.food.ChatQwen") as MockLLM:
            mock_llm = MagicMock()
            mock_llm.bind_tools.return_value.ainvoke = AsyncMock(return_value=mock_response)
            MockLLM.return_value = mock_llm

            result = await food_node(state)

    assert "foods" in result
    assert isinstance(result["foods"], list)
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_agents.py::test_food_agent_returns_list -v
```
预期：`ModuleNotFoundError`

- [ ] **Step 3: 实现 `app/agent/travel/food.py`**

```python
# app/agent/travel/food.py
from textwrap import dedent
from typing import Dict, Any, List

from langchain_core.messages import HumanMessage, BaseMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState
from app.agent.travel.mcp_utils import get_travel_mcp_client
from app.agent.travel.attraction import _run_react_loop, _parse_json_list

_PROMPT = {
    "zh": dedent("""
        你是美食推荐专家。为{destination}的旅行安排美食计划。

        偏好：{preferences}
        人均餐饮预算：{food_budget:.0f}元/天
        活动区域：{areas}

        使用 dianping_restaurant_search 搜索餐厅，用 dianping_menu 查看招牌菜。
        按早/午/晚餐推荐，覆盖不同菜系和价位。

        以 JSON 数组格式输出，每项包含：name、cuisine、avg_price_per_person、address、signature_dishes、meal_type（breakfast/lunch/dinner）、reason。
        只输出 JSON，不要其他文字。
    """).strip(),
    "en": dedent("""
        You are a food expert. Plan dining for a trip to {destination}.

        Preferences: {preferences}
        Daily food budget: {food_budget:.0f} CNY/person
        Activity areas: {areas}

        Use dianping_restaurant_search and dianping_menu. Cover breakfast, lunch, and dinner.

        Output as JSON array: name, cuisine, avg_price_per_person, address, signature_dishes, meal_type, reason.
        JSON only.
    """).strip(),
}


async def food_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== FoodAgent：推荐美食 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"
    destination = trip.destination if trip else ""
    days = trip.days if trip else 3
    budget = trip.budget if trip else 3000.0
    food_budget = (budget * 0.3) / days  # 30% of budget for food
    preferences = ", ".join(trip.preferences) if trip and trip.preferences else ("无特定偏好" if lang == "zh" else "none")

    attractions = state.get("attractions", [])
    areas = ", ".join({a.get("address", "").split("区")[0] + "区" for a in attractions[:3] if "区" in a.get("address", "")}) or destination

    try:
        mcp_client = await get_travel_mcp_client(["dianping"])
        tools = await mcp_client.get_tools()
        tool_map = {t.name: t for t in tools}
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0)
        llm_with_tools = llm.bind_tools(tools) if tools else llm

        prompt = _PROMPT[lang].format(
            destination=destination, preferences=preferences,
            food_budget=food_budget, areas=areas,
        )
        messages: List[BaseMessage] = [HumanMessage(content=prompt)]
        final_text = await _run_react_loop(messages, llm_with_tools, tool_map)
        foods = _parse_json_list(final_text)
        logger.info(f"FoodAgent 完成，推荐 {len(foods)} 个餐厅")
        return {"foods": foods}

    except Exception as e:
        logger.error(f"FoodAgent 失败: {e}", exc_info=True)
        return {"foods": [], "errors": {"food": str(e)}}
```

- [ ] **Step 4: 运行测试**

```
pytest tests/agent/travel/test_agents.py::test_food_agent_returns_list -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/food.py
git commit -m "feat: add FoodAgent (Dianping restaurant search with meal planning)"
```

---

## Task 11: StrategyAgent

**Files:**
- Create: `app/agent/travel/strategy.py`

- [ ] **Step 1: 追加测试**

```python
# 追加到 tests/agent/travel/test_agents.py
@pytest.mark.asyncio
async def test_strategy_agent_returns_plan():
    from app.agent.travel.strategy import strategy_node

    state = _make_full_state()
    state["attractions"] = [{"name": "大熊猫基地"}]
    state["route"] = {"days": [{"day": 1, "attractions": ["大熊猫基地"]}]}
    state["hotels"] = [{"name": "香格里拉酒店", "price_per_night": 1200}]
    state["foods"] = [{"name": "大龙燚火锅", "meal_type": "dinner"}]

    mock_response = MagicMock()
    mock_response.content = "# 成都3日游攻略\n\n## Day 1\n大熊猫基地..."

    with patch("app.agent.travel.strategy.ChatQwen") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result = await strategy_node(state)

    assert "final_plan" in result
    assert len(result["final_plan"]) > 0


@pytest.mark.asyncio
async def test_strategy_agent_english_output():
    from app.agent.travel.strategy import strategy_node

    state = _make_full_state(language="en")
    state["route"] = {}
    state["hotels"] = []
    state["foods"] = []

    mock_response = MagicMock()
    mock_response.content = "# Chengdu 3-Day Travel Guide\n\n## Day 1..."

    with patch("app.agent.travel.strategy.ChatQwen") as MockLLM:
        MockLLM.return_value.ainvoke = AsyncMock(return_value=mock_response)
        result = await strategy_node(state)

    assert "final_plan" in result
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_agents.py::test_strategy_agent_returns_plan -v
```
预期：`ModuleNotFoundError`

- [ ] **Step 3: 实现 `app/agent/travel/strategy.py`**

```python
# app/agent/travel/strategy.py
import json
from textwrap import dedent
from typing import Dict, Any

from langchain_core.messages import HumanMessage
from langchain_qwq import ChatQwen
from loguru import logger

from app.config import config
from app.agent.travel.state import TravelPlanState

_SYSTEM = {
    "zh": dedent("""
        你是资深旅游攻略专家。根据以下信息，生成一份完整的逐日旅游攻略。

        攻略要求：
        - 按天组织，每天包含：上午/下午/晚上的安排
        - 每个景点说明参观时长和注意事项
        - 每顿饭推荐具体餐厅和招牌菜
        - 每晚住宿说明酒店名称和价格
        - 结尾加上交通、天气、行李等实用Tips
        - 格式使用 Markdown，清晰易读

        如果某类信息缺失（标注"暂不可用"），跳过该部分，用通用建议代替。
    """).strip(),
    "en": dedent("""
        You are an expert travel planner. Generate a complete day-by-day travel guide.

        Requirements:
        - Organize by day: morning/afternoon/evening
        - Include duration and tips for each attraction
        - Recommend specific restaurants for each meal
        - Include hotel name and price for each night
        - End with practical tips: transport, weather, packing
        - Use Markdown format

        If any data is marked "unavailable", skip and use general advice instead.
    """).strip(),
}


def _build_context(state: TravelPlanState, lang: str) -> str:
    trip = state["trip_params"]
    errors = state.get("errors", {})

    def safe(data, label):
        if not data:
            return f"{label}: {'暂不可用' if lang == 'zh' else 'unavailable'}\n"
        return f"{label}:\n{json.dumps(data, ensure_ascii=False, indent=2)}\n"

    ctx = ""
    if trip:
        ctx += f"旅行参数: {trip.model_dump_json(ensure_ascii=False)}\n\n" if lang == "zh" else f"Trip params: {trip.model_dump_json()}\n\n"
    ctx += safe(state.get("attractions"), "景点列表" if lang == "zh" else "Attractions")
    ctx += safe(state.get("route"), "路线规划" if lang == "zh" else "Route")
    ctx += safe(state.get("hotels"), "酒店选项" if lang == "zh" else "Hotels")
    ctx += safe(state.get("foods"), "美食推荐" if lang == "zh" else "Food")

    if errors:
        ctx += f"\n注意，以下数据获取失败（已用内置知识补充）：{list(errors.keys())}\n" if lang == "zh" \
            else f"\nNote: The following data failed to load (using built-in knowledge): {list(errors.keys())}\n"
    return ctx


async def strategy_node(state: TravelPlanState) -> Dict[str, Any]:
    logger.info("=== StrategyAgent：生成完整攻略 ===")
    trip = state["trip_params"]
    lang = trip.language if trip else "zh"

    context = _build_context(state, lang)
    system_prompt = _SYSTEM[lang]
    prompt = context + ("\n\n请生成完整攻略：" if lang == "zh" else "\n\nPlease generate the complete travel guide:")

    try:
        llm = ChatQwen(model=config.rag_model, api_key=config.dashscope_api_key, temperature=0.3)
        response = await llm.ainvoke([HumanMessage(content=system_prompt + "\n\n" + prompt)])
        final_plan = response.content if hasattr(response, "content") else str(response)
        logger.info(f"StrategyAgent 完成，攻略长度: {len(final_plan)} 字符")
        return {"final_plan": final_plan}
    except Exception as e:
        logger.error(f"StrategyAgent 失败: {e}", exc_info=True)
        # Fallback: concatenate raw data
        fallback = f"攻略生成失败，以下是原始数据：\n{context}" if lang == "zh" else f"Guide generation failed. Raw data:\n{context}"
        return {"final_plan": fallback, "errors": {"strategy": str(e)}}
```

- [ ] **Step 4: 运行测试**

```
pytest tests/agent/travel/test_agents.py -v
```
预期：全部 PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/strategy.py
git commit -m "feat: add StrategyAgent (bilingual travel guide synthesis)"
```

---

## Task 12: Main Orchestration Graph

**Files:**
- Create: `app/agent/travel/graph.py`

- [ ] **Step 1: 写测试**

```python
# 追加到 tests/agent/travel/test_agents.py
@pytest.mark.asyncio
async def test_graph_build():
    from app.agent.travel.graph import build_travel_graph
    graph = build_travel_graph()
    assert graph is not None


@pytest.mark.asyncio
async def test_graph_initial_state_shape():
    from app.agent.travel.graph import make_initial_state
    state = make_initial_state("帮我规划成都3日游")
    assert state["user_input"] == "帮我规划成都3日游"
    assert state["attractions"] == []
    assert state["errors"] == {}
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/agent/travel/test_agents.py::test_graph_build -v
```
预期：`ModuleNotFoundError`

- [ ] **Step 3: 实现 `app/agent/travel/graph.py`**

```python
# app/agent/travel/graph.py
from typing import List
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from loguru import logger

from app.agent.travel.state import TravelPlanState
from app.agent.travel.parser import parser_node
from app.agent.travel.attraction import attraction_node
from app.agent.travel.route import route_node
from app.agent.travel.hotel import hotel_node
from app.agent.travel.food import food_node
from app.agent.travel.strategy import strategy_node


def _dispatch_parallel(state: TravelPlanState) -> List[Send]:
    """阶段2：AttractionAgent 完成后，并行派发 Route/Hotel/Food"""
    logger.info("并行派发 Route/Hotel/Food Agent")
    return [
        Send("route_agent", state),
        Send("hotel_agent", state),
        Send("food_agent", state),
    ]


def build_travel_graph():
    """构建三阶段旅游规划图"""
    workflow = StateGraph(TravelPlanState)

    # 注册节点
    workflow.add_node("parser", parser_node)
    workflow.add_node("attraction_agent", attraction_node)
    workflow.add_node("route_agent", route_node)
    workflow.add_node("hotel_agent", hotel_node)
    workflow.add_node("food_agent", food_node)
    workflow.add_node("strategy_agent", strategy_node)

    # 阶段1：串行
    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "attraction_agent")

    # 阶段2：并行分发（Send API）
    workflow.add_conditional_edges(
        "attraction_agent",
        _dispatch_parallel,
        ["route_agent", "hotel_agent", "food_agent"],
    )

    # 阶段3：并行结果汇入 strategy（所有分支完成后自动触发）
    workflow.add_edge("route_agent", "strategy_agent")
    workflow.add_edge("hotel_agent", "strategy_agent")
    workflow.add_edge("food_agent", "strategy_agent")
    workflow.add_edge("strategy_agent", END)

    return workflow.compile()


def make_initial_state(user_input: str) -> TravelPlanState:
    return {
        "user_input": user_input,
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }
```

- [ ] **Step 4: 运行测试**

```
pytest tests/agent/travel/test_agents.py::test_graph_build tests/agent/travel/test_agents.py::test_graph_initial_state_shape -v
```
预期：PASS

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/graph.py
git commit -m "feat: add main travel orchestration graph (3-phase: serial → parallel → strategy)"
```

---

## Task 13: Models & Service

**Files:**
- Create: `app/models/travel.py`
- Create: `app/services/travel_service.py`
- Create: `tests/api/__init__.py`
- Create: `tests/api/test_travel.py`

- [ ] **Step 1: 写测试**

```python
# tests/api/test_travel.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_travel_service_yields_events():
    from app.services.travel_service import travel_service

    async def mock_stream(*args, **kwargs):
        yield {"strategy_agent": {"final_plan": "成都3日游攻略..."}}

    with patch.object(travel_service, "_graph") as mock_graph:
        mock_graph.astream = mock_stream
        events = []
        async for event in travel_service.plan(user_input="帮我规划成都3日游"):
            events.append(event)

    assert any(e.get("type") == "complete" for e in events)


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
```

- [ ] **Step 2: 运行，确认失败**

```
pytest tests/api/test_travel.py -v
```
预期：`ModuleNotFoundError`

- [ ] **Step 3: 创建 `app/models/travel.py`**

```python
# app/models/travel.py
from typing import Optional
from pydantic import BaseModel, Field
from app.agent.travel.state import TripParams


class TripRequest(BaseModel):
    user_input: str = Field(default="", description="自然语言旅行需求描述")
    trip_params: Optional[TripParams] = Field(default=None, description="结构化旅行参数（优先级高于 user_input）")
    session_id: str = Field(default="default", description="会话ID")

    class Config:
        json_schema_extra = {
            "example": {
                "user_input": "帮我规划一个五天四夜的成都之旅，预算5000元，喜欢吃辣和历史文化",
                "session_id": "session-001"
            }
        }
```

- [ ] **Step 4: 创建 `app/services/travel_service.py`**

```python
# app/services/travel_service.py
from typing import AsyncGenerator, Dict, Any, Optional
from loguru import logger

from app.agent.travel.graph import build_travel_graph, make_initial_state
from app.agent.travel.state import TripParams


class TravelService:

    def __init__(self):
        self._graph = build_travel_graph()
        logger.info("TravelService 初始化完成")

    async def plan(
        self,
        user_input: str = "",
        trip_params: Optional[TripParams] = None,
        session_id: str = "default",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """执行旅游规划，流式返回进度事件"""
        # 构建初始状态
        effective_input = user_input
        initial = make_initial_state(effective_input)
        if trip_params:
            initial["trip_params"] = trip_params
            if not effective_input:
                initial["user_input"] = f"规划{trip_params.destination}{trip_params.days}日游"

        logger.info(f"[会话 {session_id}] 开始旅游规划: {effective_input or trip_params}")

        config_dict = {"configurable": {"thread_id": session_id}}

        try:
            async for event in self._graph.astream(
                input=initial,
                config=config_dict,
                stream_mode="updates",
            ):
                for node_name, node_output in event.items():
                    yield self._format_event(node_name, node_output)

            final_state = self._graph.get_state(config_dict)
            final_plan = ""
            if final_state and final_state.values:
                final_plan = final_state.values.get("final_plan", "")

            yield {"type": "complete", "message": "规划完成" if final_plan else "规划完成（无攻略输出）", "final_plan": final_plan}
            logger.info(f"[会话 {session_id}] 规划完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] 规划失败: {e}", exc_info=True)
            yield {"type": "error", "message": f"规划出错: {str(e)}"}

    @staticmethod
    def _format_event(node_name: str, output: dict | None) -> Dict[str, Any]:
        _LABELS = {
            "parser": ("parsing", "解析旅行参数..."),
            "attraction_agent": ("attractions", "正在搜索景点..."),
            "route_agent": ("route", "正在规划路线..."),
            "hotel_agent": ("hotels", "正在搜索酒店..."),
            "food_agent": ("food", "正在推荐美食..."),
            "strategy_agent": ("strategy", "正在生成完整攻略..."),
        }
        stage, message = _LABELS.get(node_name, (node_name, f"{node_name} 执行中"))
        event: Dict[str, Any] = {"type": "progress", "stage": stage, "message": message}
        if output:
            if node_name == "strategy_agent" and output.get("final_plan"):
                event["content"] = output["final_plan"]
            elif node_name == "attraction_agent" and output.get("attractions"):
                event["attractions"] = output["attractions"]
        return event


travel_service = TravelService()
```

- [ ] **Step 5: 创建 `tests/api/__init__.py`**

```python
# tests/api/__init__.py
# (empty)
```

- [ ] **Step 6: 运行测试**

```
pytest tests/api/test_travel.py -v
```
预期：全部 PASS

- [ ] **Step 7: Commit**

```bash
git add app/models/travel.py app/services/travel_service.py tests/api/__init__.py tests/api/test_travel.py
git commit -m "feat: add travel models and service (SSE streaming with progress events)"
```

---

## Task 14: API Endpoint

**Files:**
- Create: `app/api/travel.py`
- Modify: `app/main.py`

- [ ] **Step 1: 写 API 测试**

```python
# 追加到 tests/api/test_travel.py
from fastapi.testclient import TestClient


def test_travel_plan_endpoint_exists():
    from app.main import app
    client = TestClient(app)
    # POST with empty body should return 422 (validation error) not 404
    resp = client.post("/api/travel/plan", json={})
    assert resp.status_code != 404
```

- [ ] **Step 2: 运行，确认失败（返回 404）**

```
pytest tests/api/test_travel.py::test_travel_plan_endpoint_exists -v
```
预期：FAIL（404 Not Found）

- [ ] **Step 3: 创建 `app/api/travel.py`**

```python
# app/api/travel.py
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from app.models.travel import TripRequest
from app.services.travel_service import travel_service

router = APIRouter()


@router.post("/travel/plan")
async def plan_trip(request: TripRequest):
    """
    旅游规划接口（流式 SSE）

    支持两种输入方式：
    1. 自然语言：`{"user_input": "帮我规划5天成都之旅，预算5000元"}`
    2. 结构化：`{"trip_params": {"destination": "成都", "days": 5, "budget": 5000}}`

    **SSE 事件类型：**
    - `progress` — Agent 进度：`{"type":"progress","stage":"attractions","message":"正在搜索景点..."}`
    - `complete` — 规划完成：`{"type":"complete","final_plan":"完整攻略文本..."}`
    - `error` — 错误：`{"type":"error","message":"..."}`
    """
    session_id = request.session_id or "default"
    logger.info(f"[会话 {session_id}] 收到旅游规划请求")

    async def event_generator():
        try:
            async for event in travel_service.plan(
                user_input=request.user_input,
                trip_params=request.trip_params,
                session_id=session_id,
            ):
                yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}
                if event.get("type") in ("complete", "error"):
                    break
        except Exception as e:
            logger.error(f"[会话 {session_id}] SSE 异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
```

- [ ] **Step 4: 修改 `app/main.py`**

第 16 行将：
```python
from app.api import chat, health, file, aiops
```
改为：
```python
from app.api import chat, health, file, travel
```

第 65 行将：
```python
app.include_router(aiops.router, prefix="/api", tags=["AIOps智能运维"])
```
改为：
```python
app.include_router(travel.router, prefix="/api", tags=["旅游规划"])
```

第 49 行将：
```python
    description="基于 LangChain 的智能oncall运维系统",
```
改为：
```python
    description="基于 LangChain 的旅游多智能体规划系统",
```

- [ ] **Step 5: 运行测试**

```
pytest tests/api/test_travel.py -v
```
预期：全部 PASS

- [ ] **Step 6: Commit**

```bash
git add app/api/travel.py app/main.py
git commit -m "feat: add travel API endpoint (POST /api/travel/plan SSE) and update main.py"
```

---

## Task 15: Cleanup & Final Wiring

**Files:**
- Delete: `app/agent/aiops/` (directory)
- Delete: `app/api/aiops.py`
- Delete: `app/models/aiops.py`
- Delete: `app/services/aiops_service.py`
- Modify: `app/agent/__init__.py` (if imports aiops)

- [ ] **Step 1: 运行全量测试，确认现有测试通过**

```
pytest tests/ -v --ignore=tests/agent/travel --ignore=tests/api
```
预期：无 travel 相关测试失败（旧测试可能失败，这是预期的）

- [ ] **Step 2: 删除 AIOps 相关文件**

```bash
# Windows PowerShell
Remove-Item -Recurse -Force app/agent/aiops
Remove-Item -Force app/api/aiops.py
Remove-Item -Force app/models/aiops.py
Remove-Item -Force app/services/aiops_service.py
```

- [ ] **Step 3: 检查是否有残留 aiops 导入**

```bash
grep -r "aiops" app/ --include="*.py"
```
预期：无输出（main.py 已在 Task 14 中更新）

- [ ] **Step 4: 运行全量测试**

```
pytest tests/agent/travel/ tests/api/ -v
```
预期：所有旅游相关测试 PASS

- [ ] **Step 5: 验证服务可启动**

```bash
python -m app.main
```
预期：服务启动于 http://0.0.0.0:9900，访问 http://localhost:9900/docs 可见 `/api/travel/plan` 接口

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m "feat: complete travel agent system - remove aiops, wire travel pipeline"
```

---

## 启动说明

在正式运行前，先启动三个 MCP Server（各开一个终端）：

```bash
# 终端1
python mcp_servers/gaode_maps.py    # http://localhost:8010

# 终端2
python mcp_servers/ctrip.py         # http://localhost:8011

# 终端3
python mcp_servers/dianping.py      # http://localhost:8012

# 终端4（主服务）
python -m app.main                  # http://localhost:9900
```

`.env` 需要配置（最少配置）：
```
DASHSCOPE_API_KEY=your_qwen_api_key
GAODE_API_KEY=your_gaode_api_key    # 从 https://lbs.amap.com 获取
```

测试请求：
```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{"user_input": "帮我规划一个5天成都之旅，预算5000元，喜欢美食和历史"}' \
  --no-buffer
```
