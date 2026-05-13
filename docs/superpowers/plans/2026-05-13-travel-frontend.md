# Travel Frontend Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将旅游规划 Tab 升级为完整工作台：结构化表单输入、按天卡片可视化、高德地图集成、打印导出、持久化分享链接。

**Architecture:** 后端新增 `structured_plan` JSON 字段（由 strategy_agent 从 state 数据组装，无额外 LLM 调用）、SQLite 持久化分享存储、`/map-key` + `/share` 接口。前端新增 `TravelUI` 类管理旅游规划 Tab 的独立两栏布局（左栏：表单→进度→卡片；右栏：高德地图），与聊天功能完全隔离。

**Tech Stack:** FastAPI, SQLAlchemy 2.x + SQLite, Pydantic v2, 高德地图 JS SDK 2.0, Vanilla JS (ES2020), SSE streaming

---

## File Map

| 文件 | 操作 |
|------|------|
| `pyproject.toml` | 新增 `sqlalchemy>=2.0` 直接依赖 |
| `app/agent/travel/state.py` | 新增 `structured_plan: Optional[dict]` |
| `app/agent/travel/attraction.py` | 提示词增加 `lng`, `lat` 输出字段 |
| `app/agent/travel/hotel.py` | 提示词增加 `lng`, `lat` 输出字段 |
| `app/agent/travel/strategy.py` | 新增 `_build_structured_plan()` + 返回 `structured_plan` |
| `app/services/travel_service.py` | `complete` 事件透传 `structured_plan` |
| `app/db/__init__.py` | 新建，空包 |
| `app/db/share_store.py` | SQLAlchemy 模型 + `create_tables()` + CRUD |
| `app/config.py` | 新增 `amap_js_key`, `share_db_url` |
| `.env` | 新增 `AMAP_JS_KEY`, `SHARE_DB_URL` |
| `app/models/travel.py` | 新增 `ShareRequest`, `ShareResponse` |
| `app/api/travel.py` | 新增 `/map-key`, `/share` POST/GET |
| `app/main.py` | lifespan 调用 `create_tables()` |
| `static/index.html` | 新增 `#travelLayout` 两栏 HTML + share modal |
| `static/styles.css` | 新增旅游布局/表单/卡片/进度/地图/打印/modal 样式 |
| `static/app.js` | 新增 `TravelUI` 类；更新 `switchAppMode` / `updateUI` |
| `tests/api/test_travel.py` | 新增 share + map-key 接口测试 |
| `tests/db/__init__.py` | 新建 |
| `tests/db/test_share_store.py` | share_store CRUD 测试 |

---

## Task 1: 依赖 + State 新增 structured_plan + lng/lat 字段

**Files:**
- Modify: `pyproject.toml`
- Modify: `app/agent/travel/state.py`
- Modify: `app/agent/travel/attraction.py`
- Modify: `app/agent/travel/hotel.py`

- [ ] **Step 1: 在 `pyproject.toml` 新增 sqlalchemy 直接依赖**

在 `dependencies` 列表末尾加一行：

```toml
    "sqlalchemy>=2.0.0",
```

- [ ] **Step 2: 同步依赖**

```bash
uv sync
```

Expected: 无报错，`sqlalchemy` 已在 `.venv` 中（原为传递依赖，现升为直接依赖）。

- [ ] **Step 3: 在 `state.py` 新增 `structured_plan` 字段**

在 `class TravelPlanState(TypedDict):` 末尾添加：

```python
# app/agent/travel/state.py  — 在 final_plan: str 后面加一行
    structured_plan: Optional[dict]
```

完整 `TravelPlanState` 变为：

```python
class TravelPlanState(TypedDict):
    user_input: str
    trip_params: Optional[TripParams]
    attractions: List[dict]
    route: dict
    hotels: List[dict]
    foods: List[dict]
    final_plan: str
    structured_plan: Optional[dict]
    errors: Annotated[dict, merge_dicts]
    messages: Annotated[List[BaseMessage], add_messages]
```

- [ ] **Step 4: 在 `attraction.py` 提示词增加 `lng`, `lat` 输出字段**

找到 zh 提示词：
```
最终以 JSON 数组格式输出景点，每项包含：name、address、rating、ticket_price、highlights、reason。
```
改为：
```
最终以 JSON 数组格式输出景点，每项包含：name、address、rating、ticket_price、highlights、reason、lng（经度，浮点数）、lat（纬度，浮点数）。坐标从高德 POI 搜索结果中提取，若无则省略。
```

找到 en 提示词：
```
Output as a JSON array only. Each item: name, address, rating, ticket_price, highlights, reason.
```
改为：
```
Output as a JSON array only. Each item: name, address, rating, ticket_price, highlights, reason, lng (longitude float), lat (latitude float). Extract coordinates from gaode POI results; omit if unavailable.
```

- [ ] **Step 5: 在 `hotel.py` 提示词增加 `lng`, `lat` 输出字段**

找到 zh 提示词：
```
以 JSON 数组格式输出，每项包含：name、stars、rating、price_per_night、address、amenities、reason。
```
改为：
```
以 JSON 数组格式输出，每项包含：name、stars、rating、price_per_night、address、amenities、reason、lng（经度，浮点数）、lat（纬度，浮点数）。坐标从携程酒店详情中提取，若无则省略。
```

找到 en 提示词：
```
Output as JSON array: name, stars, rating, price_per_night, address, amenities, reason.
```
改为：
```
Output as JSON array: name, stars, rating, price_per_night, address, amenities, reason, lng (longitude float), lat (latitude float). Extract from ctrip hotel detail; omit if unavailable.
```

- [ ] **Step 6: 更新 `test_state.py` 验证新字段**

在 `tests/agent/travel/test_state.py` 末尾追加：

```python
def test_travel_plan_state_structured_plan():
    state: TravelPlanState = {
        "user_input": "test",
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "structured_plan": None,
        "errors": {},
        "messages": [],
    }
    assert state["structured_plan"] is None
```

- [ ] **Step 7: 运行测试确认通过**

```bash
uv run pytest tests/agent/travel/test_state.py -v
```

Expected: 所有测试 PASS（包含新的 `test_travel_plan_state_structured_plan`）。

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml app/agent/travel/state.py app/agent/travel/attraction.py app/agent/travel/hotel.py tests/agent/travel/test_state.py
git commit -m "feat: add structured_plan to state; add lng/lat to attraction/hotel output"
```

---

## Task 2: Strategy Agent 生成 structured_plan

**Files:**
- Modify: `app/agent/travel/strategy.py`

- [ ] **Step 1: 在 `strategy.py` 添加 `_build_structured_plan()` 函数**

在 `strategy_node` 函数之前插入：

```python
def _build_structured_plan(state: TravelPlanState) -> dict:
    """Assemble structured day-by-day plan from state data (no extra LLM call)."""
    trip = state.get("trip_params")
    if not trip:
        return {}

    days_count = trip.days
    attractions = state.get("attractions") or []
    hotels = state.get("hotels") or []
    food_list = state.get("foods") or []
    budget = trip.budget
    start_date = trip.start_date

    per_day_attr = max(1, (len(attractions) + days_count - 1) // days_count)
    per_day_food = max(2, (len(food_list) + days_count - 1) // days_count)

    days = []
    for i in range(1, days_count + 1):
        if start_date:
            try:
                from datetime import datetime, timedelta
                base = datetime.strptime(start_date, "%Y-%m-%d")
                day_date = (base + timedelta(days=i - 1)).strftime("%Y-%m-%d")
            except ValueError:
                day_date = f"第{i}天"
        else:
            day_date = f"第{i}天"

        day_attr_raw = attractions[(i - 1) * per_day_attr: i * per_day_attr]
        day_attractions = []
        for a in day_attr_raw:
            highlights = a.get("highlights", "")
            tip = highlights[0] if isinstance(highlights, list) and highlights else str(highlights)
            entry: dict = {"name": a.get("name", ""), "duration": "2h", "tip": tip}
            if a.get("lng"):
                entry["lng"] = a["lng"]
            if a.get("lat"):
                entry["lat"] = a["lat"]
            day_attractions.append(entry)

        hotel_raw = hotels[0] if hotels else {}
        day_hotel: dict = {
            "name": hotel_raw.get("name", ""),
            "price_per_night": hotel_raw.get("price_per_night", 0),
        }
        if hotel_raw.get("lng"):
            day_hotel["lng"] = hotel_raw["lng"]
        if hotel_raw.get("lat"):
            day_hotel["lat"] = hotel_raw["lat"]

        meal_type_map = {"breakfast": "早餐", "lunch": "午餐", "dinner": "晚餐"}
        day_foods_raw = food_list[(i - 1) * per_day_food: i * per_day_food]
        meals = [
            {
                "type": meal_type_map.get(f.get("meal_type", "lunch"), f.get("meal_type", "午餐")),
                "name": f.get("name", ""),
                "price": f.get("avg_price_per_person", 80),
            }
            for f in day_foods_raw
        ]

        days.append({
            "day": i,
            "date": day_date,
            "attractions": day_attractions,
            "hotel": day_hotel,
            "meals": meals,
            "estimated_cost": round(budget / days_count),
        })

    return {
        "days": days,
        "total_cost": budget,
        "tips": ["提前预订热门景点门票", "注意当地天气变化", "保留部分应急资金"],
    }
```

- [ ] **Step 2: 更新 `strategy_node` 返回 `structured_plan`**

将 `strategy_node` 函数的 return 语句从：
```python
        return {"final_plan": final_plan}
```
改为：
```python
        structured = _build_structured_plan(state)
        logger.info(f"StrategyAgent 生成 structured_plan，共 {len(structured.get('days', []))} 天")
        return {"final_plan": final_plan, "structured_plan": structured}
```

同样更新 fallback return：
```python
        return {"final_plan": fallback, "errors": {"strategy": str(e)}}
```
改为：
```python
        structured = _build_structured_plan(state)
        return {"final_plan": fallback, "structured_plan": structured, "errors": {"strategy": str(e)}}
```

- [ ] **Step 3: 写测试**

新建 `tests/agent/travel/test_strategy_structured.py`：

```python
import pytest
from app.agent.travel.strategy import _build_structured_plan
from app.agent.travel.state import TripParams


def _make_state(days=2, attractions=None, hotels=None, foods=None, start_date="2026-06-01"):
    params = TripParams(destination="成都", days=days, budget=2000.0, start_date=start_date)
    return {
        "user_input": "test",
        "trip_params": params,
        "attractions": attractions or [],
        "route": {},
        "hotels": hotels or [],
        "foods": foods or [],
        "final_plan": "",
        "structured_plan": None,
        "errors": {},
        "messages": [],
    }


def test_build_structured_plan_basic():
    state = _make_state(days=2)
    result = _build_structured_plan(state)
    assert "days" in result
    assert len(result["days"]) == 2
    assert result["total_cost"] == 2000.0
    assert "tips" in result


def test_build_structured_plan_dates():
    state = _make_state(days=3, start_date="2026-06-01")
    result = _build_structured_plan(state)
    assert result["days"][0]["date"] == "2026-06-01"
    assert result["days"][1]["date"] == "2026-06-02"
    assert result["days"][2]["date"] == "2026-06-03"


def test_build_structured_plan_distributes_attractions():
    attractions = [
        {"name": "宽窄巷子", "highlights": "历史街区", "lng": 104.06, "lat": 30.67},
        {"name": "锦里", "highlights": "民俗文化"},
        {"name": "武侯祠", "highlights": "三国文化"},
        {"name": "春熙路", "highlights": "购物"},
    ]
    state = _make_state(days=2, attractions=attractions)
    result = _build_structured_plan(state)
    # 4 attractions distributed over 2 days = 2 per day
    assert len(result["days"][0]["attractions"]) == 2
    assert len(result["days"][1]["attractions"]) == 2


def test_build_structured_plan_coordinates_included():
    attractions = [{"name": "宽窄巷子", "highlights": [], "lng": 104.06, "lat": 30.67}]
    state = _make_state(days=1, attractions=attractions)
    result = _build_structured_plan(state)
    attr = result["days"][0]["attractions"][0]
    assert attr["lng"] == 104.06
    assert attr["lat"] == 30.67


def test_build_structured_plan_no_trip_params():
    state = _make_state()
    state["trip_params"] = None
    result = _build_structured_plan(state)
    assert result == {}


def test_build_structured_plan_no_start_date():
    state = _make_state(days=2, start_date="")
    result = _build_structured_plan(state)
    assert result["days"][0]["date"] == "第1天"
    assert result["days"][1]["date"] == "第2天"
```

- [ ] **Step 4: 运行测试**

```bash
uv run pytest tests/agent/travel/test_strategy_structured.py -v
```

Expected: 6 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/agent/travel/strategy.py tests/agent/travel/test_strategy_structured.py
git commit -m "feat: strategy_agent assembles structured_plan JSON from state data"
```

---

## Task 3: TravelService 透传 structured_plan 到 SSE complete 事件

**Files:**
- Modify: `app/services/travel_service.py`

- [ ] **Step 1: 更新 `_format_event` 在 strategy_agent 阶段透传 `structured_plan`**

找到 `_format_event` 中：
```python
        if output:
            if node_name == "strategy_agent" and output.get("final_plan"):
                event["content"] = output["final_plan"]
            elif node_name == "attraction_agent" and output.get("attractions"):
                event["attractions"] = output["attractions"]
```
改为：
```python
        if output:
            if node_name == "strategy_agent" and output.get("final_plan"):
                event["content"] = output["final_plan"]
            if node_name == "attraction_agent" and output.get("attractions"):
                event["attractions"] = output["attractions"]
```

- [ ] **Step 2: 更新 `plan()` 方法，在 complete 事件中加入 `structured_plan`**

找到：
```python
            yield {
                "type": "complete",
                "message": "规划完成" if final_plan else "规划完成（无攻略输出）",
                "final_plan": final_plan,
            }
```
改为：
```python
            structured_plan = None
            if final_state and final_state.values:
                structured_plan = final_state.values.get("structured_plan")

            yield {
                "type": "complete",
                "message": "规划完成" if final_plan else "规划完成（无攻略输出）",
                "final_plan": final_plan,
                "structured_plan": structured_plan,
            }
```

- [ ] **Step 3: 更新已有测试，mock 中加入 `structured_plan`**

在 `tests/api/test_travel.py` 的 `test_travel_service_yields_complete_event` 中，`mock_graph.get_state` 返回值改为：
```python
        mock_graph.get_state = MagicMock(return_value=MagicMock(
            values={"final_plan": "成都3日游攻略...", "structured_plan": {"days": [], "total_cost": 3000.0, "tips": []}}
        ))
```

追加新测试：
```python
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
```

- [ ] **Step 4: 运行测试**

```bash
uv run pytest tests/api/test_travel.py -v
```

Expected: 所有测试 PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/travel_service.py tests/api/test_travel.py
git commit -m "feat: pass structured_plan through SSE complete event"
```

---

## Task 4: Config + SQLite Share Store

**Files:**
- Modify: `app/config.py`
- Modify: `.env`
- Create: `app/db/__init__.py`
- Create: `app/db/share_store.py`
- Create: `tests/db/__init__.py`
- Create: `tests/db/test_share_store.py`

- [ ] **Step 1: 在 `app/config.py` 新增两个配置项**

在 `class Settings` 中 `gaode_api_key` 后面加：

```python
    # 高德地图 JS API Key（用于前端地图展示）
    amap_js_key: str = ""
    # 分享链接数据库 URL
    share_db_url: str = "sqlite:///data/shares.db"
```

- [ ] **Step 2: 在 `.env` 新增对应变量**

在 `.env` 末尾追加：

```
# 高德地图 JS SDK Key（在 lbs.amap.com 控制台创建「Web端(JS API)」Key）
AMAP_JS_KEY=

# 分享链接数据库（默认 SQLite）
SHARE_DB_URL=sqlite:///data/shares.db
```

- [ ] **Step 3: 创建 `app/db/__init__.py`**

```python
# app/db/__init__.py
```

（空文件）

- [ ] **Step 4: 创建 `app/db/share_store.py`**

```python
# app/db/share_store.py
import json
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import Column, DateTime, String, Text, create_engine
from sqlalchemy.orm import DeclarativeBase, Session

from app.config import config


class Base(DeclarativeBase):
    pass


class SharePlan(Base):
    __tablename__ = "share_plans"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    plan = Column(Text, nullable=False)
    structured_plan = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)


def _get_engine():
    db_url = config.share_db_url
    if db_url.startswith("sqlite:///"):
        # ensure data/ directory exists
        db_path = db_url[len("sqlite:///"):]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(db_url, connect_args={"check_same_thread": False} if "sqlite" in db_url else {})


_engine = _get_engine()


def create_tables() -> None:
    Base.metadata.create_all(_engine)


def save_share(plan: str, structured_plan: dict) -> str:
    """Persist a share and return its UUID."""
    share_id = str(uuid.uuid4())
    with Session(_engine) as session:
        row = SharePlan(
            id=share_id,
            plan=plan,
            structured_plan=json.dumps(structured_plan, ensure_ascii=False),
        )
        session.add(row)
        session.commit()
    return share_id


def get_share(share_id: str) -> dict | None:
    """Return {plan, structured_plan} or None if not found."""
    with Session(_engine) as session:
        row = session.get(SharePlan, share_id)
        if row is None:
            return None
        return {
            "plan": row.plan,
            "structured_plan": json.loads(row.structured_plan),
        }
```

- [ ] **Step 5: 写 share_store 测试**

新建 `tests/db/__init__.py`（空文件）。

新建 `tests/db/test_share_store.py`：

```python
# tests/db/test_share_store.py
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path):
    """Redirect share store to a temp SQLite DB for each test."""
    db_url = f"sqlite:///{tmp_path}/test_shares.db"
    with patch("app.db.share_store.config") as mock_cfg:
        mock_cfg.share_db_url = db_url
        # Rebuild engine and tables with temp DB
        import app.db.share_store as store
        store._engine = store._get_engine()
        store.create_tables()
        yield
        # Cleanup: drop tables
        store.Base.metadata.drop_all(store._engine)


def test_save_and_get_share():
    from app.db.share_store import save_share, get_share

    share_id = save_share("# 成都攻略\n内容", {"days": [{"day": 1}], "total_cost": 2000.0, "tips": []})
    assert share_id  # is a UUID string

    result = get_share(share_id)
    assert result is not None
    assert result["plan"] == "# 成都攻略\n内容"
    assert result["structured_plan"]["total_cost"] == 2000.0


def test_get_share_not_found():
    from app.db.share_store import get_share

    result = get_share("00000000-0000-0000-0000-000000000000")
    assert result is None


def test_save_share_returns_unique_ids():
    from app.db.share_store import save_share

    id1 = save_share("plan1", {})
    id2 = save_share("plan2", {})
    assert id1 != id2
```

- [ ] **Step 6: 运行测试**

```bash
uv run pytest tests/db/test_share_store.py -v
```

Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add app/config.py .env app/db/ tests/db/
git commit -m "feat: add SQLite share store with SQLAlchemy; add amap_js_key config"
```

---

## Task 5: API 端点：/map-key、/share POST/GET + 初始化 DB

**Files:**
- Modify: `app/models/travel.py`
- Modify: `app/api/travel.py`
- Modify: `app/main.py`

- [ ] **Step 1: 在 `app/models/travel.py` 新增 Share 模型**

在文件末尾追加：

```python
class ShareRequest(BaseModel):
    plan: str = Field(description="Markdown 攻略文本")
    structured_plan: dict = Field(default_factory=dict, description="结构化攻略 JSON")


class ShareResponse(BaseModel):
    share_id: str
    url: str
```

- [ ] **Step 2: 在 `app/api/travel.py` 新增三个端点**

在 `router = APIRouter()` 下方，`plan_trip` 之前追加：

```python
from fastapi import Request
from app.config import config
from app.db.share_store import save_share, get_share
from app.models.travel import ShareRequest, ShareResponse


@router.get("/travel/map-key")
async def get_map_key():
    """Return the Amap JS API key (kept server-side to avoid exposing in HTML)."""
    return {"key": config.amap_js_key}


@router.post("/travel/share", response_model=ShareResponse)
async def create_share(request: Request, body: ShareRequest):
    """Persist a travel plan and return a shareable URL."""
    share_id = save_share(body.plan, body.structured_plan)
    base = str(request.base_url).rstrip("/")
    return ShareResponse(share_id=share_id, url=f"{base}/?share={share_id}")


@router.get("/travel/share/{share_id}")
async def read_share(share_id: str):
    """Retrieve a previously saved travel plan by share_id."""
    from fastapi import HTTPException
    data = get_share(share_id)
    if data is None:
        raise HTTPException(status_code=404, detail="分享链接不存在或已失效")
    return data
```

- [ ] **Step 3: 在 `app/main.py` lifespan 中初始化数据库**

找到 `lifespan` 函数：
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    ...
    yield
```
在 `yield` 之前加一行：
```python
    from app.db.share_store import create_tables
    create_tables()
    logger.info("Share DB 初始化完成")
```

- [ ] **Step 4: 写 API 测试**

在 `tests/api/test_travel.py` 末尾追加：

```python
def test_map_key_endpoint():
    import sys
    from unittest.mock import MagicMock, patch
    for mod in ["pymilvus", "langchain_milvus", "langchain_milvus.function"]:
        if mod not in sys.modules:
            sys.modules[mod] = MagicMock()

    with patch("app.db.share_store.config") as mock_cfg, \
         patch("app.db.share_store._get_engine") as mock_eng:
        mock_cfg.share_db_url = "sqlite:///:memory:"
        mock_cfg.amap_js_key = "test-amap-key"
        mock_eng.return_value = MagicMock()

        from fastapi.testclient import TestClient
        # patch config on the api module as well
        with patch("app.api.travel.config") as api_cfg:
            api_cfg.amap_js_key = "test-amap-key"
            from app.main import app
            client = TestClient(app)
            resp = client.get("/api/travel/map-key")
            assert resp.status_code == 200
            assert "key" in resp.json()


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
         patch("app.api.travel.get_share", fake_get):
        client = TestClient(app)
        resp = client.post("/api/travel/share", json={
            "plan": "# 成都攻略",
            "structured_plan": {"days": [], "total_cost": 1000.0, "tips": []}
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["share_id"] == "test-share-id-123"
        assert "share_id" in data["url"]

        resp2 = client.get(f"/api/travel/share/{data['share_id']}")
        assert resp2.status_code == 200
        assert resp2.json()["plan"] == "# 成都攻略"

        resp3 = client.get("/api/travel/share/nonexistent-id")
        assert resp3.status_code == 404
```

- [ ] **Step 5: 运行测试**

```bash
uv run pytest tests/api/test_travel.py -v -k "share or map_key"
```

Expected: 新增测试 PASS.

- [ ] **Step 6: Commit**

```bash
git add app/models/travel.py app/api/travel.py app/main.py tests/api/test_travel.py
git commit -m "feat: add /map-key, /share POST/GET endpoints; init DB in lifespan"
```

---

## Task 6: Frontend HTML — 旅游规划两栏布局

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: 在 `index.html` 的 `</main>` 之前插入 travel-layout**

找到 `</main>` 之前（即 `loadingOverlay` div 之前）插入整个 travel-layout 块：

```html
        <!-- ═══ Travel Layout (显示在旅游规划 Tab) ══════════════════════ -->
        <div class="travel-layout" id="travelLayout">
            <!-- 工具栏 -->
            <div class="travel-toolbar" id="travelToolbar">
                <span class="toolbar-title" id="travelDestTitle">旅游规划工作台</span>
                <div class="toolbar-actions">
                    <button class="toolbar-btn" id="printPlanBtn" style="display:none">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                            <polyline points="6 9 6 2 18 2 18 9" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                            <rect x="6" y="14" width="12" height="8" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                        打印 PDF
                    </button>
                    <button class="toolbar-btn toolbar-btn-primary" id="sharePlanBtn" style="display:none">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none">
                            <circle cx="18" cy="5" r="3" stroke="currentColor" stroke-width="2"/>
                            <circle cx="6" cy="12" r="3" stroke="currentColor" stroke-width="2"/>
                            <circle cx="18" cy="19" r="3" stroke="currentColor" stroke-width="2"/>
                            <line x1="8.59" y1="13.51" x2="15.42" y2="17.49" stroke="currentColor" stroke-width="2"/>
                            <line x1="15.41" y1="6.51" x2="8.59" y2="10.49" stroke="currentColor" stroke-width="2"/>
                        </svg>
                        生成分享链接
                    </button>
                </div>
            </div>

            <!-- 两栏主体 -->
            <div class="travel-body">
                <!-- 左栏 -->
                <div class="travel-left-panel">

                    <!-- 表单 -->
                    <div class="travel-form" id="travelForm">
                        <div class="form-group">
                            <label class="form-label">目的地 <span class="required">*</span></label>
                            <input type="text" id="destInput" class="form-input" placeholder="如：成都、杭州、京都">
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">出发日期</label>
                                <input type="date" id="startDateInput" class="form-input">
                            </div>
                            <div class="form-group">
                                <label class="form-label">天数</label>
                                <input type="number" id="daysInput" class="form-input" value="3" min="1" max="14">
                            </div>
                        </div>
                        <div class="form-row">
                            <div class="form-group">
                                <label class="form-label">人数</label>
                                <input type="number" id="numPeopleInput" class="form-input" value="2" min="1" max="10">
                            </div>
                            <div class="form-group">
                                <label class="form-label">预算（元）</label>
                                <input type="number" id="budgetInput" class="form-input" value="3000" min="100" step="100">
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-label">偏好标签</label>
                            <div class="pref-tags" id="prefTags">
                                <button class="pref-tag" data-pref="美食">美食</button>
                                <button class="pref-tag" data-pref="历史">历史</button>
                                <button class="pref-tag" data-pref="自然">自然</button>
                                <button class="pref-tag" data-pref="亲子">亲子</button>
                                <button class="pref-tag" data-pref="摄影">摄影</button>
                                <button class="pref-tag" data-pref="购物">购物</button>
                            </div>
                        </div>
                        <div class="form-group">
                            <label class="form-label">直接描述（可选）</label>
                            <textarea id="travelDescInput" class="form-textarea"
                                placeholder="如：帮我规划一个轻松的成都美食之旅，偏好小众景点" rows="3"></textarea>
                        </div>
                        <button class="travel-submit-btn" id="travelSubmitBtn" disabled>
                            开始规划 →
                        </button>
                    </div>

                    <!-- 进度 -->
                    <div class="travel-progress" id="travelProgress" style="display:none">
                        <h3 class="progress-title">正在为您规划...</h3>
                        <div class="progress-stages" id="progressStages"></div>
                    </div>

                    <!-- 结果卡片 -->
                    <div class="travel-result" id="travelResult" style="display:none">
                        <div class="day-cards" id="dayCards"></div>
                        <div class="cost-summary" id="costSummary"></div>
                        <button class="replan-btn" id="replanBtn">重新规划</button>
                    </div>

                </div>

                <!-- 右栏：地图 -->
                <div class="travel-right-panel map-panel" id="mapPanel">
                    <div id="amapContainer" style="width:100%;height:100%"></div>
                    <div class="map-placeholder" id="mapPlaceholder">
                        <div class="map-placeholder-icon">🗺️</div>
                        <p>规划完成后，地图将标注景点与路线</p>
                    </div>
                </div>
            </div>
        </div>
        <!-- ═══ End Travel Layout ══════════════════════════════════════ -->

        <!-- 分享弹窗 -->
        <div class="share-modal-overlay" id="shareModalOverlay" style="display:none">
            <div class="share-modal">
                <h3 class="share-modal-title">分享链接</h3>
                <p class="share-modal-desc">任何人打开此链接即可查看攻略</p>
                <div class="share-url-row">
                    <input type="text" id="shareUrlInput" class="share-url-input" readonly>
                    <button class="copy-btn" id="copyShareUrlBtn">复制</button>
                </div>
                <button class="share-modal-close" id="shareModalClose">关闭</button>
            </div>
        </div>
```

- [ ] **Step 2: 启动服务验证 HTML 正确加载**

```bash
uv run uvicorn app.main:app --port 9900 --reload
```

打开 `http://localhost:9900`，确认页面正常加载（无 JS 错误），travel-layout 默认不可见（CSS 将在下一个任务中控制）。

- [ ] **Step 3: Commit**

```bash
git add static/index.html
git commit -m "feat: add travel-layout two-column HTML with form/progress/cards/map/share-modal"
```

---

## Task 7: Frontend CSS — 旅游布局样式

**Files:**
- Modify: `static/styles.css`

- [ ] **Step 1: 在 `styles.css` 末尾追加所有旅游样式**

```css
/* ═══════════════════════════════════════════════════════════
   旅游规划布局
═══════════════════════════════════════════════════════════ */

.travel-layout {
    display: none;
    flex-direction: column;
    flex: 1;
    height: 100%;
    overflow: hidden;
}

.travel-layout.visible {
    display: flex;
}

/* 工具栏 */
.travel-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 10px 20px;
    border-bottom: 1px solid #dadce0;
    background: #fff;
    flex-shrink: 0;
}

.toolbar-title {
    font-size: 15px;
    font-weight: 500;
    color: #3c4043;
}

.toolbar-actions {
    display: flex;
    gap: 8px;
}

.toolbar-btn {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 7px 14px;
    border: 1px solid #dadce0;
    border-radius: 20px;
    background: #fff;
    color: #3c4043;
    font-size: 13px;
    cursor: pointer;
    transition: background 0.15s;
}

.toolbar-btn:hover { background: #f1f3f4; }

.toolbar-btn-primary {
    background: #1a73e8;
    color: #fff;
    border-color: #1a73e8;
}

.toolbar-btn-primary:hover { background: #1557b0; }

/* 两栏主体 */
.travel-body {
    display: flex;
    flex: 1;
    overflow: hidden;
}

/* 左栏 */
.travel-left-panel {
    width: 50%;
    min-width: 340px;
    max-width: 560px;
    overflow-y: auto;
    border-right: 1px solid #dadce0;
    background: #fff;
}

/* 右栏 */
.travel-right-panel {
    flex: 1;
    position: relative;
    background: #f8f9fa;
}

.map-placeholder {
    position: absolute;
    inset: 0;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    color: #80868b;
    gap: 12px;
    pointer-events: none;
}

.map-placeholder-icon { font-size: 48px; }

/* ═══ 表单 ═══════════════════════════════════════════════ */

.travel-form {
    padding: 24px 20px;
}

.form-group {
    margin-bottom: 16px;
}

.form-row {
    display: flex;
    gap: 12px;
}

.form-row .form-group {
    flex: 1;
}

.form-label {
    display: block;
    font-size: 13px;
    font-weight: 500;
    color: #3c4043;
    margin-bottom: 6px;
}

.required { color: #d93025; }

.form-input {
    width: 100%;
    padding: 9px 12px;
    border: 1px solid #dadce0;
    border-radius: 8px;
    font-size: 14px;
    color: #202124;
    outline: none;
    transition: border-color 0.15s;
}

.form-input:focus { border-color: #1a73e8; }

.form-textarea {
    width: 100%;
    padding: 9px 12px;
    border: 1px solid #dadce0;
    border-radius: 8px;
    font-size: 14px;
    color: #202124;
    outline: none;
    resize: vertical;
    transition: border-color 0.15s;
    font-family: inherit;
}

.form-textarea:focus { border-color: #1a73e8; }

/* 偏好标签 */
.pref-tags {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}

.pref-tag {
    padding: 5px 14px;
    border: 1px solid #dadce0;
    border-radius: 16px;
    background: #fff;
    font-size: 13px;
    color: #3c4043;
    cursor: pointer;
    transition: all 0.15s;
}

.pref-tag:hover { border-color: #1a73e8; color: #1a73e8; }

.pref-tag.active {
    background: #e8f0fe;
    border-color: #1a73e8;
    color: #1a73e8;
    font-weight: 500;
}

/* 提交按钮 */
.travel-submit-btn {
    width: 100%;
    padding: 12px;
    background: #1a73e8;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 15px;
    font-weight: 500;
    cursor: pointer;
    transition: background 0.15s;
    margin-top: 4px;
}

.travel-submit-btn:hover:not(:disabled) { background: #1557b0; }

.travel-submit-btn:disabled {
    background: #dadce0;
    color: #80868b;
    cursor: not-allowed;
}

/* ═══ 进度 ═══════════════════════════════════════════════ */

.travel-progress {
    padding: 32px 20px;
}

.progress-title {
    font-size: 15px;
    font-weight: 500;
    color: #3c4043;
    margin-bottom: 20px;
}

.progress-stages {
    display: flex;
    flex-direction: column;
    gap: 14px;
}

.progress-stage {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 14px;
    color: #3c4043;
}

.stage-icon { font-size: 16px; width: 20px; text-align: center; }

.stage-active .stage-icon {
    animation: spin 1s linear infinite;
    display: inline-block;
}

@keyframes spin {
    from { transform: rotate(0deg); }
    to { transform: rotate(360deg); }
}

.stage-done .stage-label { color: #188038; }
.stage-active .stage-label { color: #1a73e8; font-weight: 500; }

/* ═══ 按天卡片 ══════════════════════════════════════════ */

.travel-result {
    padding: 16px 20px;
}

.day-cards {
    display: flex;
    flex-direction: column;
    gap: 12px;
}

.day-card {
    border: 1px solid #dadce0;
    border-radius: 12px;
    overflow: hidden;
}

.day-card-header {
    display: flex;
    align-items: center;
    padding: 14px 16px;
    background: #f8f9fa;
    cursor: pointer;
    user-select: none;
    transition: background 0.15s;
}

.day-card-header:hover { background: #f1f3f4; }

.day-card.highlight .day-card-header { background: #e8f0fe; }

.day-card-title {
    font-weight: 500;
    font-size: 14px;
    flex: 1;
}

.day-card-cost {
    font-size: 13px;
    color: #1a73e8;
    font-weight: 500;
    margin-right: 8px;
}

.day-card-toggle {
    font-size: 12px;
    color: #80868b;
    transition: transform 0.2s;
}

.day-card:not(.expanded) .day-card-toggle { transform: rotate(-90deg); }

.day-card-body {
    display: none;
    padding: 14px 16px;
    border-top: 1px solid #f1f3f4;
}

.day-card.expanded .day-card-body { display: block; }

.card-section {
    display: flex;
    gap: 8px;
    margin-bottom: 10px;
    font-size: 13px;
    color: #3c4043;
}

.card-section:last-child { margin-bottom: 0; }

.card-section-icon { flex-shrink: 0; width: 20px; }

.card-section ul {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 4px;
}

.card-section ul li { line-height: 1.5; }

.card-section ul li em {
    font-style: normal;
    color: #f29900;
    font-size: 12px;
}

.cost-summary {
    text-align: center;
    padding: 12px;
    font-size: 14px;
    color: #3c4043;
    font-weight: 500;
    border-top: 1px solid #dadce0;
    margin-top: 12px;
}

.replan-btn {
    display: block;
    width: 100%;
    margin-top: 12px;
    padding: 10px;
    border: 1px solid #dadce0;
    border-radius: 8px;
    background: #fff;
    font-size: 13px;
    color: #3c4043;
    cursor: pointer;
    transition: background 0.15s;
}

.replan-btn:hover { background: #f1f3f4; }

/* ═══ 分享弹窗 ══════════════════════════════════════════ */

.share-modal-overlay {
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.4);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 1000;
}

.share-modal {
    background: #fff;
    border-radius: 16px;
    padding: 28px;
    width: 420px;
    max-width: 90vw;
    box-shadow: 0 8px 32px rgba(0,0,0,0.15);
}

.share-modal-title {
    font-size: 18px;
    font-weight: 500;
    margin-bottom: 8px;
}

.share-modal-desc {
    font-size: 13px;
    color: #80868b;
    margin-bottom: 16px;
}

.share-url-row {
    display: flex;
    gap: 8px;
    margin-bottom: 16px;
}

.share-url-input {
    flex: 1;
    padding: 9px 12px;
    border: 1px solid #dadce0;
    border-radius: 8px;
    font-size: 13px;
    color: #3c4043;
    outline: none;
    background: #f8f9fa;
}

.copy-btn {
    padding: 9px 16px;
    background: #1a73e8;
    color: #fff;
    border: none;
    border-radius: 8px;
    font-size: 13px;
    cursor: pointer;
    white-space: nowrap;
    transition: background 0.15s;
}

.copy-btn:hover { background: #1557b0; }

.share-modal-close {
    display: block;
    width: 100%;
    padding: 10px;
    border: 1px solid #dadce0;
    border-radius: 8px;
    background: #fff;
    font-size: 14px;
    cursor: pointer;
    transition: background 0.15s;
}

.share-modal-close:hover { background: #f1f3f4; }

/* ═══ 打印样式 ══════════════════════════════════════════ */

@media print {
    .sidebar,
    .travel-toolbar,
    .travel-form,
    .travel-progress,
    .map-panel,
    .replan-btn,
    .current-mode-badge { display: none !important; }

    .travel-body { display: block; }
    .travel-left-panel { width: 100%; max-width: 100%; border: none; }
    .travel-result { padding: 0; }
    .day-card-body { display: block !important; }
}
```

- [ ] **Step 2: 验证**

刷新 `http://localhost:9900`，点击「旅游规划」Tab 确认布局生效（此时 JS 尚未完整接管，但 CSS class 控制可用）。

- [ ] **Step 3: Commit**

```bash
git add static/styles.css
git commit -m "feat: add travel layout/form/cards/map/print/share-modal CSS"
```

---

## Task 8: Frontend JS — TravelUI 类（表单 + 进度 + 卡片）

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 在 `app.js` 末尾（`document.addEventListener` 之前）插入 `TravelUI` 类**

在文件最后的 `document.addEventListener('DOMContentLoaded', ...)` 之前插入：

```javascript
// ═══════════════════════════════════════════════════════════
// TravelUI — 旅游规划工作台
// ═══════════════════════════════════════════════════════════

class TravelUI {
    constructor(app) {
        this.app = app;
        this.mapInstance = null;
        this.mapLoaded = false;
        this.markers = [];
        this.polylines = [];
        this.currentPlan = null;
        this.currentStructured = null;

        this._STAGES = [
            { stage: 'parsing',     label: '解析旅行参数' },
            { stage: 'attractions', label: '搜索景点推荐' },
            { stage: 'route',       label: '规划路线' },
            { stage: 'hotels',      label: '搜索酒店' },
            { stage: 'food',        label: '推荐美食' },
            { stage: 'strategy',    label: '生成完整攻略' },
        ];

        this._initElements();
        this._bindEvents();
    }

    _initElements() {
        this.form           = document.getElementById('travelForm');
        this.destInput      = document.getElementById('destInput');
        this.startDateInput = document.getElementById('startDateInput');
        this.daysInput      = document.getElementById('daysInput');
        this.numPeopleInput = document.getElementById('numPeopleInput');
        this.budgetInput    = document.getElementById('budgetInput');
        this.prefTagsEl     = document.getElementById('prefTags');
        this.descInput      = document.getElementById('travelDescInput');
        this.submitBtn      = document.getElementById('travelSubmitBtn');
        this.progressEl     = document.getElementById('travelProgress');
        this.progressStages = document.getElementById('progressStages');
        this.resultEl       = document.getElementById('travelResult');
        this.dayCardsEl     = document.getElementById('dayCards');
        this.costSummaryEl  = document.getElementById('costSummary');
        this.replanBtn      = document.getElementById('replanBtn');
        this.printBtn       = document.getElementById('printPlanBtn');
        this.shareBtn       = document.getElementById('sharePlanBtn');
        this.shareOverlay   = document.getElementById('shareModalOverlay');
        this.shareUrlInput  = document.getElementById('shareUrlInput');
        this.copyBtn        = document.getElementById('copyShareUrlBtn');
        this.shareClose     = document.getElementById('shareModalClose');
        this.mapPlaceholder = document.getElementById('mapPlaceholder');
        this.destTitle      = document.getElementById('travelDestTitle');

        // set default date = today
        const today = new Date().toISOString().split('T')[0];
        if (this.startDateInput) this.startDateInput.value = today;
    }

    _bindEvents() {
        this.destInput?.addEventListener('input', () => this._updateSubmitState());
        this.prefTagsEl?.addEventListener('click', e => {
            if (e.target.classList.contains('pref-tag')) {
                e.target.classList.toggle('active');
            }
        });
        this.submitBtn?.addEventListener('click', () => this._startPlanning());
        this.replanBtn?.addEventListener('click', () => this._resetToForm());
        this.printBtn?.addEventListener('click', () => window.print());
        this.shareBtn?.addEventListener('click', () => this._generateShareLink());
        this.copyBtn?.addEventListener('click', () => this._copyShareUrl());
        this.shareClose?.addEventListener('click', () => this._closeShareModal());
        this.shareOverlay?.addEventListener('click', e => {
            if (e.target === this.shareOverlay) this._closeShareModal();
        });
    }

    _updateSubmitState() {
        if (this.submitBtn) {
            this.submitBtn.disabled = !this.destInput?.value.trim();
        }
    }

    _getSelectedPrefs() {
        return [...(this.prefTagsEl?.querySelectorAll('.pref-tag.active') || [])]
            .map(el => el.dataset.pref);
    }

    _buildRequestBody() {
        return {
            user_input: this.descInput?.value.trim() || '',
            trip_params: {
                destination: this.destInput?.value.trim() || '',
                start_date: this.startDateInput?.value || '',
                days: parseInt(this.daysInput?.value) || 3,
                num_people: parseInt(this.numPeopleInput?.value) || 2,
                budget: parseFloat(this.budgetInput?.value) || 3000,
                preferences: this._getSelectedPrefs(),
                language: 'zh',
            },
            session_id: this.app.sessionId,
        };
    }

    // ─── Progress ─────────────────────────────────────────────────────────────

    _showProgress() {
        if (this.form) this.form.style.display = 'none';
        if (this.progressEl) this.progressEl.style.display = '';
        if (this.resultEl) this.resultEl.style.display = 'none';
        if (this.printBtn) this.printBtn.style.display = 'none';
        if (this.shareBtn) this.shareBtn.style.display = 'none';

        if (this.progressStages) {
            this.progressStages.innerHTML = this._STAGES.map(s => `
                <div class="progress-stage" id="ps-${s.stage}">
                    <span class="stage-icon">⬜</span>
                    <span class="stage-label">${s.label}</span>
                </div>`).join('');
        }
    }

    _updateProgress(stage) {
        let found = false;
        for (const s of this._STAGES) {
            const el = document.getElementById(`ps-${s.stage}`);
            if (!el) continue;
            const icon = el.querySelector('.stage-icon');
            if (s.stage === stage) {
                el.className = 'progress-stage stage-active';
                icon.textContent = '⏳';
                found = true;
            } else if (!found) {
                el.className = 'progress-stage stage-done';
                icon.textContent = '✅';
            }
        }
    }

    _markAllStagesDone() {
        this._STAGES.forEach(s => {
            const el = document.getElementById(`ps-${s.stage}`);
            if (!el) return;
            el.className = 'progress-stage stage-done';
            el.querySelector('.stage-icon').textContent = '✅';
        });
    }

    // ─── Day Cards ────────────────────────────────────────────────────────────

    _showResult(structured) {
        if (this.progressEl) this.progressEl.style.display = 'none';
        if (this.resultEl) this.resultEl.style.display = '';
        if (this.printBtn) this.printBtn.style.display = '';
        if (this.shareBtn) this.shareBtn.style.display = '';

        if (!structured?.days?.length) {
            if (this.dayCardsEl) this.dayCardsEl.innerHTML = '<p style="color:#80868b;padding:12px">攻略已生成（无结构化预览）</p>';
            return;
        }

        if (this.dayCardsEl) {
            this.dayCardsEl.innerHTML = structured.days.map(d => this._renderDayCard(d)).join('');
            this.dayCardsEl.querySelectorAll('.day-card-header').forEach(header => {
                header.addEventListener('click', () => {
                    const card = header.closest('.day-card');
                    card.classList.toggle('expanded');
                    const dayNum = parseInt(card.dataset.day);
                    this._highlightDay(dayNum);
                });
            });
        }

        const body = this._buildRequestBody();
        if (this.costSummaryEl) {
            this.costSummaryEl.textContent =
                `总预算 ¥${structured.total_cost} / ${structured.days.length}天 · ${body.trip_params.num_people}人`;
        }
    }

    _renderDayCard(day) {
        const date = day.date || `第${day.day}天`;
        const attrHtml = (day.attractions || []).map(a =>
            `<li><strong>${this._esc(a.name)}</strong>${a.duration ? ` · ${a.duration}` : ''}${a.tip ? ` <em>💡${this._esc(a.tip)}</em>` : ''}</li>`
        ).join('');
        const mealHtml = (day.meals || []).map(m =>
            `<li>${this._esc(m.type)} · ${this._esc(m.name)}${m.price ? ` ¥${m.price}` : ''}</li>`
        ).join('');
        const hotel = day.hotel || {};
        const hotelHtml = hotel.name
            ? `<div class="card-section"><span class="card-section-icon">🏨</span><ul><li>${this._esc(hotel.name)}${hotel.price_per_night ? ` ¥${hotel.price_per_night}/晚` : ''}</li></ul></div>`
            : '';

        return `<div class="day-card expanded" data-day="${day.day}">
            <div class="day-card-header">
                <span class="day-card-title">📅 第 ${day.day} 天 · ${this._esc(date)}</span>
                <span class="day-card-cost">${day.estimated_cost ? `¥${day.estimated_cost}` : ''}</span>
                <span class="day-card-toggle">▼</span>
            </div>
            <div class="day-card-body">
                ${attrHtml ? `<div class="card-section"><span class="card-section-icon">🏛️</span><ul>${attrHtml}</ul></div>` : ''}
                ${mealHtml ? `<div class="card-section"><span class="card-section-icon">🍜</span><ul>${mealHtml}</ul></div>` : ''}
                ${hotelHtml}
            </div>
        </div>`;
    }

    _esc(str) {
        if (!str) return '';
        return String(str).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }

    _resetToForm() {
        this.currentPlan = null;
        this.currentStructured = null;
        if (this.resultEl) this.resultEl.style.display = 'none';
        if (this.form) this.form.style.display = '';
        if (this.printBtn) this.printBtn.style.display = 'none';
        if (this.shareBtn) this.shareBtn.style.display = 'none';
        if (this.destTitle) this.destTitle.textContent = '旅游规划工作台';
        this._clearMap();
    }

    // ─── Planning Flow ────────────────────────────────────────────────────────

    async startPlanning() {
        this._showProgress();
        this._clearMap();
        await this._loadMap();

        const body = this._buildRequestBody();
        if (this.destTitle) {
            this.destTitle.textContent = `正在规划 · ${body.trip_params.destination}`;
        }

        try {
            const resp = await fetch('/api/travel/plan', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(body),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);

            const reader = resp.body.getReader();
            const decoder = new TextDecoder();
            let buf = '';

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                buf += decoder.decode(value, { stream: true });
                const lines = buf.split('\n');
                buf = lines.pop() || '';
                for (const line of lines) {
                    if (!line.startsWith('data:')) continue;
                    try {
                        const event = JSON.parse(line.slice(5).trim());
                        this._handleEvent(event);
                    } catch (_) {}
                }
            }
        } catch (e) {
            this._showError(e.message);
        }
    }

    _startPlanning() { this.startPlanning(); }

    _handleEvent(event) {
        if (event.type === 'progress') {
            this._updateProgress(event.stage);
            if (event.stage === 'attractions' && event.attractions?.length) {
                this._addMarkers(event.attractions, 'attraction');
            }
        } else if (event.type === 'complete') {
            this.currentPlan = event.final_plan;
            this.currentStructured = event.structured_plan;
            this._markAllStagesDone();
            const dest = this._buildRequestBody().trip_params.destination;
            if (this.destTitle) this.destTitle.textContent = `${dest} 攻略`;
            setTimeout(() => {
                this._showResult(this.currentStructured);
                if (this.currentStructured) {
                    this._renderMapFromStructured(this.currentStructured);
                }
            }, 600);
        } else if (event.type === 'error') {
            this._showError(event.message);
        }
    }

    _showError(msg) {
        if (this.progressEl) this.progressEl.style.display = 'none';
        if (this.form) this.form.style.display = '';
        alert(`规划失败：${msg}`);
    }
}
```

- [ ] **Step 2: 验证类定义无语法错误**

```bash
node --input-type=module < static/app.js 2>&1 | head -5
```

Expected: 无输出（无语法错误）。若报错，根据错误行号修正。

- [ ] **Step 3: Commit（仅类骨架，地图和分享方法在后续任务加入）**

```bash
git add static/app.js
git commit -m "feat: add TravelUI class with form/progress/cards logic"
```

---

## Task 9: Frontend JS — 高德地图集成

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 在 `TravelUI` 类的 `_showError` 方法之后，追加地图方法**

```javascript
    // ─── Amap Map ─────────────────────────────────────────────────────────────

    async _loadMap() {
        if (this.mapLoaded) return;
        try {
            const resp = await fetch('/api/travel/map-key');
            if (!resp.ok) return;
            const { key } = await resp.json();
            if (!key) return;

            await new Promise((resolve, reject) => {
                const s = document.createElement('script');
                s.src = `https://webapi.amap.com/maps?v=2.0&key=${encodeURIComponent(key)}&plugin=AMap.Polyline`;
                s.onload = resolve;
                s.onerror = reject;
                document.head.appendChild(s);
            });

            this.mapInstance = new window.AMap.Map('amapContainer', {
                zoom: 11,
                center: [104.065735, 30.659462],
            });
            this.mapLoaded = true;
            if (this.mapPlaceholder) this.mapPlaceholder.style.display = 'none';
        } catch (e) {
            console.warn('[TravelUI] 地图加载失败:', e);
        }
    }

    _clearMap() {
        if (!this.mapInstance) return;
        this.markers.forEach(m => m.setMap(null));
        this.polylines.forEach(p => p.setMap(null));
        this.markers = [];
        this.polylines = [];
    }

    _addMarkers(items, type) {
        if (!this.mapInstance || !window.AMap) return;
        const imgBlue = 'https://webapi.amap.com/theme/v1.3/markers/n/mark_b.png';
        const imgRed  = 'https://webapi.amap.com/theme/v1.3/markers/n/mark_r.png';
        const imgUrl  = type === 'hotel' ? imgRed : imgBlue;

        items.forEach(item => {
            if (!item.lng || !item.lat) return;
            const marker = new window.AMap.Marker({
                position: [item.lng, item.lat],
                title: item.name || '',
                map: this.mapInstance,
                icon: new window.AMap.Icon({
                    image: imgUrl,
                    size: new window.AMap.Size(19, 31),
                    imageSize: new window.AMap.Size(19, 31),
                }),
            });
            const label = type === 'hotel' ? `🏨 ${item.name}` : `🏛️ ${item.name}`;
            const info = new window.AMap.InfoWindow({
                content: `<div style="padding:6px 10px;font-size:13px">${label}</div>`,
                offset: new window.AMap.Pixel(0, -30),
            });
            marker.on('click', () => info.open(this.mapInstance, marker.getPosition()));
            this.markers.push(marker);
        });
    }

    _renderMapFromStructured(structured) {
        if (!this.mapInstance || !window.AMap || !structured?.days) return;

        const COLORS = ['#4A90E2', '#E2574A', '#50C878', '#FF8C00', '#9B59B6', '#1ABC9C', '#F39C12'];
        const allLngLat = [];

        structured.days.forEach((day, idx) => {
            const pts = [];
            (day.attractions || []).forEach(a => {
                if (a.lng && a.lat) { pts.push([a.lng, a.lat]); allLngLat.push([a.lng, a.lat]); }
            });
            if (day.hotel?.lng && day.hotel?.lat) {
                pts.push([day.hotel.lng, day.hotel.lat]);
                allLngLat.push([day.hotel.lng, day.hotel.lat]);
                this._addMarkers([day.hotel], 'hotel');
            }
            if (pts.length > 1) {
                const poly = new window.AMap.Polyline({
                    path: pts.map(p => new window.AMap.LngLat(p[0], p[1])),
                    strokeColor: COLORS[idx % COLORS.length],
                    strokeWeight: 3,
                    strokeOpacity: 0.9,
                    map: this.mapInstance,
                });
                this.polylines.push(poly);
            }
        });

        if (allLngLat.length) {
            const lngs = allLngLat.map(p => p[0]);
            const lats = allLngLat.map(p => p[1]);
            this.mapInstance.setBounds(new window.AMap.Bounds(
                new window.AMap.LngLat(Math.min(...lngs), Math.min(...lats)),
                new window.AMap.LngLat(Math.max(...lngs), Math.max(...lats)),
            ));
        }
    }

    _highlightDay(dayNum) {
        if (!this.polylines.length) return;
        this.polylines.forEach((poly, idx) => {
            const isSelected = idx + 1 === dayNum;
            poly.setOptions({
                strokeOpacity: isSelected ? 1 : 0.2,
                strokeWeight: isSelected ? 5 : 2,
            });
        });
        // highlight card
        document.querySelectorAll('.day-card').forEach(card => {
            card.classList.toggle('highlight', parseInt(card.dataset.day) === dayNum);
        });
    }
```

- [ ] **Step 2: 验证语法**

```bash
node --input-type=module < static/app.js 2>&1 | head -5
```

Expected: 无输出。

- [ ] **Step 3: Commit**

```bash
git add static/app.js
git commit -m "feat: add Amap map integration to TravelUI (markers, polylines, day highlight)"
```

---

## Task 10: Frontend JS — 分享/导出 + switchAppMode 接入

**Files:**
- Modify: `static/app.js`

- [ ] **Step 1: 在 `TravelUI` 类末尾（`_highlightDay` 之后，类的 `}` 之前）追加分享方法**

```javascript
    // ─── Share & Export ───────────────────────────────────────────────────────

    async _generateShareLink() {
        if (!this.currentPlan && !this.currentStructured) return;
        try {
            const resp = await fetch('/api/travel/share', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    plan: this.currentPlan || '',
                    structured_plan: this.currentStructured || {},
                }),
            });
            if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
            const data = await resp.json();
            if (this.shareUrlInput) this.shareUrlInput.value = data.url;
            if (this.shareOverlay) this.shareOverlay.style.display = 'flex';
        } catch (e) {
            alert('生成分享链接失败：' + e.message);
        }
    }

    async _copyShareUrl() {
        const url = this.shareUrlInput?.value;
        if (!url) return;
        try {
            await navigator.clipboard.writeText(url);
            if (this.copyBtn) {
                this.copyBtn.textContent = '已复制 ✓';
                setTimeout(() => { if (this.copyBtn) this.copyBtn.textContent = '复制'; }, 2000);
            }
        } catch (_) {
            this.shareUrlInput?.select();
        }
    }

    _closeShareModal() {
        if (this.shareOverlay) this.shareOverlay.style.display = 'none';
    }

    async loadSharedPlan(shareId) {
        try {
            const resp = await fetch(`/api/travel/share/${encodeURIComponent(shareId)}`);
            if (!resp.ok) throw new Error('分享链接不存在或已失效');
            const data = await resp.json();
            this.currentPlan = data.plan;
            this.currentStructured = data.structured_plan;

            // hide form & toolbar in read-only mode
            if (this.form) this.form.style.display = 'none';
            const toolbar = document.getElementById('travelToolbar');
            if (toolbar) toolbar.style.display = 'none';

            this._showResult(this.currentStructured);
            await this._loadMap();
            if (this.currentStructured) this._renderMapFromStructured(this.currentStructured);

            const dest = this.currentStructured?.days?.[0]?.attractions?.[0]?.name || '共享攻略';
            if (this.destTitle) this.destTitle.textContent = dest;
        } catch (e) {
            alert(e.message);
        }
    }
```

- [ ] **Step 2: 更新 `SuperBizAgentApp` 的 `constructor` — 实例化 TravelUI**

在 `constructor` 中 `this.initializeElements()` 之前加：

```javascript
        this.travelUI = new TravelUI(this);
```

- [ ] **Step 3: 更新 `switchAppMode` — 切换时显示/隐藏 travel-layout**

将现有 `switchAppMode` 方法：
```javascript
    switchAppMode(mode) {
        if (this.isStreaming) {
            this.showNotification('请等待当前操作完成后再切换模式', 'warning');
            return;
        }
        this.appMode = mode;
        document.querySelectorAll('.app-mode-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.appMode === mode);
        });
        this.updateUI();
        const label = mode === 'travel' ? '旅游规划模式' : '聊天模式';
        this.showNotification(`已切换到${label}`, 'info');
    }
```
改为：
```javascript
    switchAppMode(mode) {
        if (this.isStreaming) {
            this.showNotification('请等待当前操作完成后再切换模式', 'warning');
            return;
        }
        this.appMode = mode;
        document.querySelectorAll('.app-mode-tab').forEach(tab => {
            tab.classList.toggle('active', tab.dataset.appMode === mode);
        });

        const travelLayout = document.getElementById('travelLayout');
        const chatContainer = document.querySelector('.chat-container');
        const modeBadge = document.getElementById('currentModeBadge');

        if (mode === 'travel') {
            if (chatContainer) chatContainer.style.display = 'none';
            if (travelLayout) travelLayout.classList.add('visible');
            if (modeBadge) modeBadge.style.display = 'none';
        } else {
            if (chatContainer) chatContainer.style.display = '';
            if (travelLayout) travelLayout.classList.remove('visible');
            if (modeBadge) modeBadge.style.display = '';
            this.updateUI();
        }

        const label = mode === 'travel' ? '旅游规划模式' : '聊天模式';
        this.showNotification(`已切换到${label}`, 'info');
    }
```

- [ ] **Step 4: 在 `DOMContentLoaded` 回调中检测分享链接**

找到文件末尾的 `DOMContentLoaded` 回调：
```javascript
document.addEventListener('DOMContentLoaded', () => {
    window.__app = new SuperBizAgentApp();
});
```
改为：
```javascript
document.addEventListener('DOMContentLoaded', () => {
    const app = new SuperBizAgentApp();
    window.__app = app;

    // 检测分享链接 ?share=<id>
    const shareId = new URLSearchParams(window.location.search).get('share');
    if (shareId) {
        app.switchAppMode('travel');
        app.travelUI.loadSharedPlan(shareId);
    }
});
```

- [ ] **Step 5: 验证语法**

```bash
node --input-type=module < static/app.js 2>&1 | head -5
```

Expected: 无输出。

- [ ] **Step 6: 端到端手工验证**

```bash
uv run uvicorn app.main:app --port 9900 --reload
```

验证清单：
1. 打开 `http://localhost:9900`，点击「旅游规划」Tab → 显示表单 + 右侧地图占位符
2. 不填目的地 → 「开始规划」按钮灰色不可点
3. 填写成都，选择偏好标签 → 按钮激活
4. 点击「开始规划」→ 进度条逐步更新（需后端 MCP 可用；否则验证 SSE 事件接收即可）
5. 规划完成后 → 按天卡片展示，右侧按钮出现
6. 点击「打印 PDF」→ 浏览器打印对话框打开，地图和侧边栏不显示
7. 点击「生成分享链接」→ 弹窗显示 URL，复制按钮可用
8. 在新标签打开分享链接 → 只读模式，卡片正常显示
9. 点击「聊天」Tab → 聊天界面恢复，旅游布局隐藏

- [ ] **Step 7: Commit**

```bash
git add static/app.js
git commit -m "feat: wire TravelUI share/export/readonly; update switchAppMode for travel layout"
```

---

## 自检结果

**Spec coverage:**
- ✅ 结构化表单 → Task 1 + Task 8
- ✅ 按天卡片可视化 → Task 2 + Task 8
- ✅ 高德地图集成（真实 Key，服务端下发）→ Task 4 + Task 9
- ✅ 打印 PDF → Task 7 + Task 10
- ✅ 持久化分享链接（SQLite + SQLAlchemy）→ Task 4 + Task 5 + Task 10
- ✅ lng/lat 坐标输出 → Task 1
- ✅ 分享只读模式 → Task 10
- ✅ 进度条增强 → Task 7 + Task 8

**Type consistency check:**
- `_build_structured_plan` 在 Task 2 定义，`strategy_node` 在同一文件中调用 ✅
- `save_share` / `get_share` 在 Task 4 定义，Task 5 中调用 ✅
- `ShareRequest` / `ShareResponse` 在 Task 5 定义，api 层使用 ✅
- `TravelUI._addMarkers(items, type)` 在 Task 9 定义，Task 8 `_handleEvent` 中调用 ✅
- `TravelUI._renderMapFromStructured` 在 Task 9 定义，Task 8 `_handleEvent` 中调用 ✅
- `TravelUI._highlightDay` 在 Task 9 定义，Task 8 `_showResult` 中注册 click 调用 ✅
- `TravelUI.startPlanning` 公开方法，Task 8 内 `_startPlanning` 委托调用 ✅
