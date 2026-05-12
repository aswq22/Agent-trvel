 # 旅游多智能体系统 — 运行指南

## 系统架构概览

```
用户输入
  ↓
ParserAgent（解析旅行意图）
  ↓ 阶段1（串行）
AttractionAgent（景点推荐）← 高德地图 MCP :8010 + 大众点评 MCP :8012
  ↓ 阶段2（并行）
┌──────────────┬──────────────┬──────────────┐
RouteAgent    HotelAgent    FoodAgent
（路线规划）  （酒店推荐）  （美食推荐）
高德 :8010    携程 :8011    大众点评 :8012
└──────────────┴──────────────┴──────────────┘
  ↓ 阶段3（汇总）
StrategyAgent（生成完整攻略）
  ↓ SSE 流式输出
POST /api/travel/plan → 用户
```

---


## 环境准备

### 1. 安装依赖

```bash
cd D:/Agent/super_biz_agent

# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 2. 配置 `.env`

打开 `.env` 文件，确认以下配置：

```env
# 必填：Qwen 大模型（已配置）
DASHSCOPE_API_KEY=sk-xxxxxx
RAG_MODEL=qwen-max

# 可选：高德地图真实 API（不填则只用 Mock 数据）
# 注册地址：https://lbs.amap.com
GAODE_API_KEY=

# 携程、大众点评使用内置 Mock 数据，无需配置
```

> **说明：** 不配置 `GAODE_API_KEY` 也能完整运行，景点搜索阶段会跳过高德，只使用大众点评的 Mock 数据（成都景点 5 个、餐厅 5 家）。

---

## 启动服务

> 需要打开 **4 个终端**，分别运行以下命令。

### 终端 1 — 大众点评 MCP Server

```bash
cd D:/Agent/super_biz_agent
python mcp_servers/dianping.py
```

启动成功输出：
```
INFO:     Uvicorn running on http://0.0.0.0:8012 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

提供工具：
- `dianping_attraction_search` — 景点搜索（有 GAODE_API_KEY 则全国真实数据，否则成都 Mock）
- `dianping_restaurant_search` — 餐厅搜索（有 GAODE_API_KEY 则全国真实数据，否则成都 Mock）
- `dianping_menu` — 餐厅菜单（Mock 数据）

---

### 终端 2 — 携程酒店 MCP Server

```bash
cd D:/Agent/super_biz_agent
python mcp_servers/ctrip.py
```

启动成功输出：
```
INFO:     Uvicorn running on http://0.0.0.0:8011 (Press CTRL+C to quit)
INFO:     Application startup complete.
```

提供工具：
- `ctrip_hotel_search` — 酒店搜索（有 GAODE_API_KEY 则全国真实酒店，否则成都 Mock 4家）
- `ctrip_hotel_detail` — 酒店详情

---

### 终端 3 — 高德地图 MCP Server

```bash
cd D:/Agent/super_biz_agent
python mcp_servers/gaode_maps.py
```

启动成功输出：
```
INFO:     Uvicorn running on http://0.0.0.0:8010
```

提供工具：
- `gaode_poi_search` — POI 兴趣点搜索（需 GAODE_API_KEY）
- `gaode_route_plan` — 驾车路线规划
- `gaode_distance_matrix` — 多点距离矩阵

---

### 终端 4 — 主服务

```bash
cd D:/Agent/super_biz_agent
python -m app.main
```

启动成功输出：
```
INFO:     TravelService 初始化完成
INFO:     Uvicorn running on http://0.0.0.0:9900 (Press CTRL+C to quit)
INFO:     Started reloader process [...] using WatchFiles
INFO:     Started server process [...]
INFO:     Application startup complete.
2026-05-13 ... | INFO | main.lifespan | ============================================================
2026-05-13 ... | INFO | main.lifespan | SuperBizAgent v1.0.0 启动中...
2026-05-13 ... | INFO | main.lifespan | 监听地址: http://0.0.0.0:9900
2026-05-13 ... | INFO | main.lifespan | API 文档: http://0.0.0.0:9900/docs
2026-05-13 ... | INFO | main.lifespan | ============================================================
```

---

## 测试接口

### 方式 1：Swagger UI（最直观）

浏览器打开：**http://localhost:9900/docs**

找到 `POST /api/travel/plan` → 点击 **Try it out** → 填写请求体 → Execute

---

### 方式 2：curl 命令行

**自然语言输入：**

```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{"user_input": "帮我规划一个5天成都之旅，预算5000元，喜欢美食和历史文化"}' \
  --no-buffer
```

**结构化参数输入：**

```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{
    "trip_params": {
      "destination": "成都",
      "days": 3,
      "budget": 3000,
      "preferences": ["美食", "历史"],
      "language": "zh"
    }
  }' \
  --no-buffer
```

**英文输入（自动切换英文攻略）：**

```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Plan a 3-day trip to Chengdu, budget 500 USD, love food and history"}' \
  --no-buffer
```

---

### 方式 3：Python 脚本

```python
import httpx
import json

url = "http://localhost:9900/api/travel/plan"
payload = {
    "user_input": "帮我规划一个3天成都亲子游，预算3000元"
}

with httpx.stream("POST", url, json=payload, timeout=120) as resp:
    for line in resp.iter_lines():
        if line.startswith("data:"):
            event = json.loads(line[5:].strip())
            print(f"[{event.get('stage', event.get('type'))}] {event.get('message', '')}")
            if event.get("type") == "complete":
                print("\n=== 完整攻略 ===")
                print(event.get("final_plan", ""))
                break
```

---

## SSE 事件说明

流式输出按以下顺序推送事件：

| 事件 type | stage | 含义 |
|-----------|-------|------|
| `progress` | `parsing` | ParserAgent 正在解析旅行参数 |
| `progress` | `attractions` | AttractionAgent 搜索景点中 |
| `progress` | `route` | RouteAgent 规划路线中 |
| `progress` | `hotels` | HotelAgent 搜索酒店中 |
| `progress` | `food` | FoodAgent 推荐美食中 |
| `progress` | `strategy` | StrategyAgent 生成攻略中 |
| `complete` | — | 规划完成，`final_plan` 含完整攻略 Markdown |
| `error` | — | 发生错误，`message` 含错误信息 |

**示例输出流：**

```
data: {"type": "progress", "stage": "parsing", "message": "解析旅行参数..."}
data: {"type": "progress", "stage": "attractions", "message": "正在搜索景点..."}
data: {"type": "progress", "stage": "route", "message": "正在规划路线..."}
data: {"type": "progress", "stage": "hotels", "message": "正在搜索酒店..."}
data: {"type": "progress", "stage": "food", "message": "正在推荐美食..."}
data: {"type": "progress", "stage": "strategy", "message": "正在生成完整攻略..."}
data: {"type": "complete", "final_plan": "# 成都5日游攻略\n\n## Day 1\n..."}
```

---

## API 接口参数

### `POST /api/travel/plan`

**Request Body（二选一方式）：**

```json
{
  "user_input": "自然语言描述（与 trip_params 二选一）",
  "trip_params": {
    "destination": "成都",
    "start_date": "2026-06-01",
    "days": 5,
    "num_people": 2,
    "budget": 5000.0,
    "preferences": ["美食", "历史文化", "亲子"],
    "language": "zh"
  },
  "session_id": "my-session-001"
}
```

**字段说明：**

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `user_input` | string | `""` | 自然语言需求，与 trip_params 二选一 |
| `trip_params.destination` | string | 必填 | 目的地城市 |
| `trip_params.days` | int | `3` | 出行天数 |
| `trip_params.budget` | float | `3000` | 总预算（元） |
| `trip_params.preferences` | list | `[]` | 偏好标签 |
| `trip_params.language` | string | `"zh"` | 输出语言：`zh` 或 `en` |
| `session_id` | string | `"default"` | 会话 ID（用于区分多用户） |

---

## 运行测试套件

```bash
cd D:/Agent/super_biz_agent

# 首次需安装测试依赖（如未安装）
uv pip install pytest pytest-asyncio pytest-cov

# 运行所有旅游相关测试（不需要启动 MCP Server 或主服务）
uv run python -m pytest tests/agent/travel/ tests/api/ -v

# 预期：23 passed
```

---

## MCP Server 数据说明

| 服务 | 端口 | 有 GAODE_API_KEY | 无 GAODE_API_KEY |
|------|------|-----------------|-----------------|
| 高德地图 | 8010 | 真实路线/距离数据 | 工具调用失败，LLM 内置知识降级 |
| 携程酒店 | 8011 | **高德 POI 真实酒店数据**（全国） | Mock：成都4家酒店 |
| 大众点评 | 8012 | **高德 POI 真实景点+餐厅数据**（全国） | Mock：成都5景点+5餐厅 |

> 携程和大众点评均通过**高德地图 POI API** 提供真实数据，只需一个 Key 即可。
> 高德 POI 包含全国所有城市的酒店（070000类）、景点（110000类）、餐厅（050000类）数据。

---

## 常见问题

**Q: 请求返回 `{"type":"error","message":"规划出错:..."}` ？**
> 最常见原因是 `DASHSCOPE_API_KEY` 无效（401）。请到 https://dashscope.aliyun.com 登录后获取正确的 API Key，格式为 `sk-xxxxxxxx`，填入 `.env`。

**Q: 响应很慢？**
> Agent 调用 Qwen 大模型进行推理，每次规划通常需要 30-90 秒（包含 6 个 Agent 串/并行执行）。

**Q: 只有成都的数据？**
> 无 GAODE_API_KEY 时使用 Mock 数据（仅成都）。配置高德 API 后支持全国所有城市。

**Q: 如何接入真实携程/大众点评 API？**
> 打开对应 MCP Server 文件，将 `_mock_hotels_db` / `_mock_attractions` 替换为真实 API 调用（httpx 请求）即可，工具接口签名无需改变。高德 POI 已内置真实数据，推荐优先使用。
