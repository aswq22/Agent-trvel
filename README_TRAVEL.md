# 智能旅游规划系统 — 完整操作手册

> 基于 LangGraph 多智能体 + 高德地图 + SSE 流式输出的旅游规划工作台。

---

## 目录

1. [系统架构](#1-系统架构)
2. [环境准备](#2-环境准备)
3. [启动服务](#3-启动服务)
4. [前端使用](#4-前端使用)
5. [API 接口](#5-api-接口)
6. [SSE 事件说明](#6-sse-事件说明)
7. [调用示例](#7-调用示例)
8. [测试](#8-测试)
9. [MCP Server 数据说明](#9-mcp-server-数据说明)
10. [常见问题](#10-常见问题)
11. [变更记录](#11-变更记录)

---

## 1. 系统架构

### 后端多智能体图

```
用户输入（自然语言 或 结构化参数）
  ↓
POST /api/travel/plan
  ↓
ParserAgent ← 解析旅行意图，提取目的地/天数/预算/语言
  ↓ 阶段1（串行）
AttractionAgent ← 高德 MCP :8010  +  大众点评 MCP :8012
  ↓ 阶段2（并行，LangGraph Send()）
┌──────────────┬──────────────┬──────────────┐
│  RouteAgent  │  HotelAgent  │   FoodAgent  │
│  高德 :8010  │  携程 :8011  │  大众点评    │
│  路线规划    │  酒店推荐    │  :8012 美食  │
└──────────────┴──────────────┴──────────────┘
  ↓ 阶段3（汇总）
StrategyAgent
  ├── 生成 final_plan（Markdown 攻略）
  └── 组装 structured_plan（JSON，按天结构化）
  ↓
SSE 流式事件 → 前端实时展示
```

### 前端架构

```
浏览器 http://localhost:9900
├── 聊天模式（原有功能）
│     └── 通用问答 + RAG 文件问答
└── 旅游规划模式（本手册重点）
      ├── 左栏
      │     ├── 结构化表单（目的地/天数/预算/偏好）
      │     ├── 进度指示器（6 阶段实时更新）
      │     └── 按天卡片（景点/餐厅/酒店/费用）
      ├── 右栏
      │     └── 高德地图（景点标注 + 路线折线）
      └── 工具栏
            ├── 打印 PDF（浏览器打印）
            └── 生成分享链接（持久化到 SQLite）
```

---

## 2. 环境准备

### 2.1 Python 依赖

```bash
cd D:/Agent/super_biz_agent

# 使用 uv（推荐）
uv sync

# 或使用 pip
pip install -e .
```

### 2.2 配置 `.env`

打开 `.env`，填写以下变量：

```env
# ── 必填 ──────────────────────────────────────────────────
# 通义千问 API Key（从 https://dashscope.aliyun.com 获取）
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ── 旅游功能必填 ───────────────────────────────────────────
# 高德地图 REST API Key（景点/酒店/餐厅搜索，路线规划）
# 注册：https://lbs.amap.com → 控制台 → 创建应用 → Web 服务
GAODE_API_KEY=你的高德REST_API_KEY

# 高德地图 JS API Key（前端地图展示，与 REST Key 不同）
# 注册同上 → 创建应用 → Web 端（JS API）→ 配置白名单 localhost
AMAP_JS_KEY=你的高德JS_API_KEY

# 高德地图 JS API 安全密钥（JS API 2.0 必填）
# 在高德控制台 → 我的应用 → 对应 Key 详情页 → 安全密钥 中获取
AMAP_JS_SECURITY_CODE=你的安全密钥

# ── 可选（使用默认即可）─────────────────────────────────────
DASHSCOPE_MODEL=qwen-max
RAG_MODEL=qwen-max
SHARE_DB_URL=sqlite:///data/shares.db
PORT=9900
```

> **注意：** 高德地图涉及 **3 个凭证**，需要分别申请：
>
> | 变量 | 类型 | 用途 |
> |------|------|------|
> | `GAODE_API_KEY` | REST API Key | 后端 MCP Server 调用高德 POI/路线接口 |
> | `AMAP_JS_KEY` | JS API Key | 前端加载高德地图 SDK |
> | `AMAP_JS_SECURITY_CODE` | JS API 安全密钥 | JS API 2.0 强制要求，与 JS Key 配套 |

### 2.3 Key 申请说明

| Key 类型 | 用途 | 申请路径 |
|----------|------|---------|
| 高德 REST API Key | 后端景点/酒店/路线搜索 | lbs.amap.com → 我的应用 → 添加 Key → 服务平台选「**Web 服务**」|
| 高德 JS API Key | 前端地图渲染 | lbs.amap.com → 我的应用 → 添加 Key → 服务平台选「**Web 端（JS API）**」→ 配置域名白名单填 `localhost` |
| 高德 JS API 安全密钥 | JS API 2.0 安全验证 | 高德控制台 → 我的应用 → 点击对应 JS Key → **安全密钥**（同一页面）|
| 通义千问 Key | LLM 推理 | dashscope.aliyun.com → API Keys |

> **安全密钥说明：** 高德 JS API 2.0 引入了 `securityJsCode` 机制。本项目通过后端接口 `/api/travel/map-key` 将安全密钥下发到前端，前端在加载地图 SDK 前设置 `window._AMapSecurityConfig = { securityJsCode: '...' }`，符合高德官方推荐的明文传输模式。

> **不填任何 Key 也能运行**，但：
> - 无 `GAODE_API_KEY`：景点/酒店/餐厅搜索降级为成都 Mock 数据
> - 无 `AMAP_JS_KEY` / `AMAP_JS_SECURITY_CODE`：前端地图不加载，显示占位符

---

## 3. 启动服务

需要打开 **4 个终端**，分别启动 3 个 MCP Server 和主服务。

### 终端 1 — 大众点评 MCP（景点 + 餐厅）

```bash
cd D:/Agent/super_biz_agent
python mcp_servers/dianping.py
```

成功标志：
```
INFO:     Uvicorn running on http://0.0.0.0:8012 (Press CTRL+C to quit)
```

提供的工具：
- `dianping_attraction_search` — 景点搜索
- `dianping_restaurant_search` — 餐厅搜索
- `dianping_menu` — 餐厅菜单

---

### 终端 2 — 携程酒店 MCP

```bash
cd D:/Agent/super_biz_agent
python mcp_servers/ctrip.py
```

成功标志：
```
INFO:     Uvicorn running on http://0.0.0.0:8011 (Press CTRL+C to quit)
```

提供的工具：
- `ctrip_hotel_search` — 酒店搜索
- `ctrip_hotel_detail` — 酒店详情

---

### 终端 3 — 高德地图 MCP（路线 + POI）

```bash
cd D:/Agent/super_biz_agent
python mcp_servers/gaode_maps.py
```

成功标志：
```
INFO:     Uvicorn running on http://0.0.0.0:8010
```

提供的工具：
- `gaode_poi_search` — POI 兴趣点搜索
- `gaode_route_plan` — 驾车路线规划
- `gaode_distance_matrix` — 多点距离矩阵

---

### 终端 4 — 主服务

```bash
cd D:/Agent/super_biz_agent
uv run uvicorn app.main:app --host 0.0.0.0 --port 9900 --reload
```

成功标志：
```
INFO | SuperBizAgent v1.2.1 启动中...
INFO | Share DB 初始化完成
INFO | TravelService 初始化完成
INFO | Uvicorn running on http://0.0.0.0:9900
```

**访问地址：**
- 前端界面：http://localhost:9900
- Swagger 文档：http://localhost:9900/docs

---

## 4. 前端使用

### 4.1 进入旅游规划模式

打开 http://localhost:9900，点击左侧边栏的「**旅游规划**」Tab，界面切换为两栏工作台：

```
┌─────────────────┬───────────────────────────────────────────┐
│  侧边栏          │  [打印 PDF]  [生成分享链接]（规划完成后出现）│
│                 ├──────────────────┬────────────────────────┤
│  ● 聊天          │  结构化表单       │  高德地图               │
│  ● 旅游规划 ←   │  ──             │  （规划前：占位符）      │
│                 │  进度条（规划中） │  （规划后：景点标注）    │
│                 │  按天卡片（完成） │                        │
└─────────────────┴──────────────────┴────────────────────────┘
```

### 4.2 填写规划表单

| 字段 | 说明 | 示例 |
|------|------|------|
| 目的地 * | 必填，支持全国城市 | `成都` |
| 出发日期 | 默认今天 | `2026-06-01` |
| 天数 | 1–14 天，默认 3 | `5` |
| 人数 | 1–10 人，默认 2 | `2` |
| 预算（元） | 总预算，默认 3000 | `5000` |
| 偏好标签 | 多选，可不选 | 美食、历史 |
| 直接描述 | 可选，自然语言优先 | `帮我规划一个轻松的成都美食之旅` |

> 填写「直接描述」后，系统以自然语言为主，表单字段作为补充参数。

### 4.3 开始规划

点击「**开始规划 →**」，表单切换为进度指示器：

```
✅ 解析旅行参数
✅ 搜索景点推荐
⏳ 规划路线       ← 当前执行中（转圈动画）
⬜ 搜索酒店
⬜ 推荐美食
⬜ 生成完整攻略
```

规划完成（约 30–90 秒）后，左栏展示**按天卡片**，右栏地图自动标注景点和路线。

### 4.4 查看按天卡片

每天一张卡片，点击标题可展开/折叠：

```
┌────────────────────────────────────────────┐
│ 📅 第 1 天 · 2026-06-01          ¥1000 ▼  │
├────────────────────────────────────────────┤
│ 🏛️ 景点                                   │
│   · 宽窄巷子 · 2h  💡避开午间人流           │
│   · 锦里古街 · 1.5h                       │
├────────────────────────────────────────────┤
│ 🍜 餐饮  午餐·陈麻婆豆腐 ¥60             │
├────────────────────────────────────────────┤
│ 🏨 住宿  锦江宾馆 ¥380/晚               │
└────────────────────────────────────────────┘
```

**点击某天卡片** → 地图高亮该天路线，其余天路线变淡。

卡片底部显示：`总预算 ¥5000 / 5天 · 2人`

### 4.5 地图交互

- **蓝色图钉** — 景点位置
- **红色图钉** — 酒店位置
- **彩色折线** — 每天行程路线（不同天用不同颜色）
- **点击图钉** — 弹出信息窗口（景点/酒店名称）
- 地图自动缩放到所有标记范围

### 4.6 导出 PDF

点击右上角「**打印 PDF**」→ 浏览器打印对话框 → 目标打印机选「另存为 PDF」。

打印预览效果：
- 侧边栏、工具栏、地图不显示
- 所有天卡片展开，全宽布局
- 适合 A4 纸横/竖打印

### 4.7 生成分享链接

点击右上角「**生成分享链接**」→ 弹窗显示唯一 URL：

```
https://localhost:9900/?share=a1b2c3d4-...
```

点击「**复制**」→ 发送给他人 → 对方打开链接 → 自动切换到旅游规划模式 → 只读展示攻略和地图（无表单和工具栏）。

> 分享链接**永久有效**（存储在 `data/shares.db`，服务重启不失效）。

### 4.8 重新规划

攻略展示后点击「**重新规划**」→ 回到表单，地图清空，可修改参数重新生成。

---

## 5. API 接口

所有接口前缀：`http://localhost:9900/api`

### 5.1 规划旅程（SSE 流式）

```
POST /api/travel/plan
Content-Type: application/json
```

**请求体（二选一方式）：**

```json
// 方式 A：自然语言
{
  "user_input": "帮我规划5天成都之旅，预算5000元，喜欢美食和历史文化",
  "session_id": "session-001"
}

// 方式 B：结构化参数
{
  "trip_params": {
    "destination": "成都",
    "start_date": "2026-06-01",
    "days": 5,
    "num_people": 2,
    "budget": 5000.0,
    "preferences": ["美食", "历史"],
    "language": "zh"
  },
  "session_id": "session-001"
}

// 方式 C：两者结合（自然语言优先，结构化参数作补充）
{
  "user_input": "偏好小众景点，不要太商业化",
  "trip_params": {
    "destination": "成都",
    "days": 3,
    "budget": 3000
  }
}
```

**字段说明：**

| 字段 | 类型 | 默认 | 说明 |
|------|------|------|------|
| `user_input` | string | `""` | 自然语言描述 |
| `trip_params.destination` | string | 必填 | 目的地城市 |
| `trip_params.start_date` | string | `""` | 出发日期，格式 `YYYY-MM-DD` |
| `trip_params.days` | int | `3` | 天数（1–14） |
| `trip_params.num_people` | int | `2` | 人数 |
| `trip_params.budget` | float | `3000` | 总预算（元） |
| `trip_params.preferences` | list | `[]` | 偏好标签 |
| `trip_params.language` | string | `"zh"` | `"zh"` 或 `"en"` |
| `session_id` | string | `"default"` | 会话 ID |

**响应：** SSE 流式事件，见 [第 6 节](#6-sse-事件说明)。

---

### 5.2 获取高德地图 JS Key

```
GET /api/travel/map-key
```

**响应：**
```json
{
  "key": "你的AMAP_JS_KEY",
  "security_code": "你的安全密钥"
}
```

> Key 和安全密钥均保存在后端 `.env`，通过此接口下发，避免硬编码在 HTML 中。前端收到后在加载地图 SDK 前执行：
> ```js
> window._AMapSecurityConfig = { securityJsCode: security_code };
> ```

---

### 5.3 保存分享链接

```
POST /api/travel/share
Content-Type: application/json
```

**请求体：**
```json
{
  "plan": "# 成都5日游攻略\n\n## 第1天\n...",
  "structured_plan": {
    "days": [...],
    "total_cost": 5000.0,
    "tips": ["提前预订", "注意天气"]
  }
}
```

**响应：**
```json
{
  "share_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "url": "http://localhost:9900/?share=a1b2c3d4-..."
}
```

---

### 5.4 读取分享链接

```
GET /api/travel/share/{share_id}
```

**响应：**
```json
{
  "plan": "# 成都5日游攻略\n...",
  "structured_plan": {
    "days": [...],
    "total_cost": 5000.0,
    "tips": [...]
  }
}
```

**404 响应（链接不存在）：**
```json
{"detail": "分享链接不存在或已失效"}
```

---

### 5.5 健康检查

```
GET /api/health
```

---

## 6. SSE 事件说明

`POST /api/travel/plan` 返回 SSE 流，按以下顺序推送事件：

| type | stage | 附加字段 | 含义 |
|------|-------|---------|------|
| `progress` | `parsing` | — | ParserAgent 解析旅行参数 |
| `progress` | `attractions` | `attractions: [{name, lng?, lat?}]` | AttractionAgent 完成，含景点列表 |
| `progress` | `route` | — | RouteAgent 规划路线 |
| `progress` | `hotels` | — | HotelAgent 搜索酒店 |
| `progress` | `food` | — | FoodAgent 推荐美食 |
| `progress` | `strategy` | — | StrategyAgent 生成攻略 |
| `complete` | — | `final_plan`, `structured_plan` | 规划完成 |
| `error` | — | `message` | 发生错误 |

### 完整事件流示例

```
data: {"type": "progress", "stage": "parsing", "message": "解析旅行参数..."}

data: {"type": "progress", "stage": "attractions", "message": "正在搜索景点...",
       "attractions": [
         {"name": "宽窄巷子", "address": "成都市青羊区", "rating": 4.8,
          "lng": 104.0617, "lat": 30.6701},
         {"name": "锦里古街", "address": "成都市武侯区", "rating": 4.7,
          "lng": 104.0474, "lat": 30.6413}
       ]}

data: {"type": "progress", "stage": "route", "message": "正在规划路线..."}

data: {"type": "progress", "stage": "hotels", "message": "正在搜索酒店..."}

data: {"type": "progress", "stage": "food", "message": "正在推荐美食..."}

data: {"type": "progress", "stage": "strategy", "message": "正在生成完整攻略..."}

data: {"type": "complete",
       "message": "规划完成",
       "final_plan": "# 成都5日游攻略\n\n## 第1天\n...",
       "structured_plan": {
         "days": [
           {
             "day": 1,
             "date": "2026-06-01",
             "attractions": [
               {"name": "宽窄巷子", "duration": "2h", "tip": "避开午间人流",
                "lng": 104.0617, "lat": 30.6701}
             ],
             "hotel": {"name": "锦江宾馆", "price_per_night": 380,
                       "lng": 104.0839, "lat": 30.6510},
             "meals": [
               {"type": "午餐", "name": "陈麻婆豆腐", "price": 60},
               {"type": "晚餐", "name": "老码头火锅", "price": 120}
             ],
             "estimated_cost": 1000
           }
         ],
         "total_cost": 5000.0,
         "tips": ["提前预订热门景点门票", "注意当地天气变化", "保留部分应急资金"]
       }}
```

---

## 7. 调用示例

### 7.1 curl — 自然语言请求

```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{"user_input": "帮我规划一个5天成都之旅，预算5000元，喜欢美食和历史文化"}' \
  --no-buffer
```

### 7.2 curl — 结构化参数

```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{
    "trip_params": {
      "destination": "成都",
      "start_date": "2026-06-01",
      "days": 5,
      "num_people": 2,
      "budget": 5000,
      "preferences": ["美食", "历史"],
      "language": "zh"
    }
  }' \
  --no-buffer
```

### 7.3 curl — 英文攻略

```bash
curl -X POST http://localhost:9900/api/travel/plan \
  -H "Content-Type: application/json" \
  -d '{"user_input": "Plan a 3-day trip to Chengdu, budget 500 USD, love food and history"}' \
  --no-buffer
```

### 7.4 curl — 创建分享链接

```bash
curl -X POST http://localhost:9900/api/travel/share \
  -H "Content-Type: application/json" \
  -d '{
    "plan": "# 成都攻略\n内容...",
    "structured_plan": {"days": [], "total_cost": 5000, "tips": []}
  }'
# 返回：{"share_id": "xxx", "url": "http://localhost:9900/?share=xxx"}
```

### 7.5 Python — 完整流式消费

```python
import httpx
import json

url = "http://localhost:9900/api/travel/plan"
payload = {
    "user_input": "帮我规划一个3天成都亲子游，预算3000元",
    "trip_params": {
        "destination": "成都",
        "days": 3,
        "budget": 3000,
        "preferences": ["亲子", "美食"]
    }
}

with httpx.stream("POST", url, json=payload, timeout=120) as resp:
    for line in resp.iter_lines():
        if not line.startswith("data:"):
            continue
        event = json.loads(line[5:].strip())

        if event["type"] == "progress":
            print(f"[{event['stage']}] {event['message']}")
            if event.get("attractions"):
                print(f"  → 找到 {len(event['attractions'])} 个景点")

        elif event["type"] == "complete":
            print("\n=== 完整攻略（Markdown）===")
            print(event["final_plan"][:500], "...")

            plan = event.get("structured_plan", {})
            print(f"\n=== 结构化数据：共 {len(plan.get('days', []))} 天 ===")
            for day in plan.get("days", []):
                print(f"第 {day['day']} 天 ({day['date']})：预估费用 ¥{day['estimated_cost']}")
                for a in day.get("attractions", []):
                    print(f"  景点：{a['name']}")
            break

        elif event["type"] == "error":
            print(f"错误：{event['message']}")
            break
```

### 7.6 Python — 读取分享链接

```python
import httpx

share_id = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"
resp = httpx.get(f"http://localhost:9900/api/travel/share/{share_id}")

if resp.status_code == 200:
    data = resp.json()
    print(data["plan"][:200])
    print(f"共 {len(data['structured_plan']['days'])} 天行程")
else:
    print("链接已失效")
```

### 7.7 JavaScript — 前端调用

```javascript
const resp = await fetch('/api/travel/plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
        user_input: '帮我规划成都3日游',
        trip_params: { destination: '成都', days: 3, budget: 3000 }
    })
});

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
        const event = JSON.parse(line.slice(5).trim());
        if (event.type === 'complete') {
            console.log('攻略：', event.final_plan);
            console.log('结构化：', event.structured_plan);
        }
    }
}
```

---

## 8. 测试

```bash
cd D:/Agent/super_biz_agent

# 运行全部测试（不需要启动 MCP Server 或主服务）
uv run pytest tests/ -v

# 只运行旅游相关测试
uv run pytest tests/agent/travel/ tests/api/ tests/db/ -v

# 预期结果
# tests/agent/travel/test_state.py        9 passed
# tests/agent/travel/test_parser.py       x passed
# tests/agent/travel/test_agents.py       x passed
# tests/agent/travel/test_strategy_structured.py  6 passed
# tests/api/test_travel.py               7 passed
# tests/db/test_share_store.py           3 passed
# 共计 36 passed
```

---

## 9. MCP Server 数据说明

| 服务 | 端口 | 有 `GAODE_API_KEY` | 无 `GAODE_API_KEY` |
|------|------|-------------------|-------------------|
| 高德地图 | 8010 | 真实 POI + 路线数据（全国） | 工具调用失败，LLM 降级为内置知识 |
| 携程酒店 | 8011 | 高德 POI 真实酒店（全国） | Mock：成都 4 家酒店 |
| 大众点评 | 8012 | 高德 POI 真实景点+餐厅（全国） | Mock：成都 5 景点 + 5 餐厅 |

> 携程和大众点评均通过**高德地图 POI API** 补充真实数据，只需配置 `GAODE_API_KEY` 即可全国覆盖。

### MCP 容错机制

- 每个 MCP 工具调用**自动重试 2 次**
- 全部失败后 Agent 降级使用 LLM 内置知识继续规划（不影响整体流程）
- 部分数据失败时，`errors` 字段记录失败原因，攻略仍然完整生成

---

## 10. 常见问题

**Q：请求返回 `{"type":"error","message":"规划出错:..."}` ？**
> 最常见原因是 `DASHSCOPE_API_KEY` 无效（401）。到 https://dashscope.aliyun.com 获取正确的 Key（格式 `sk-xxxxxxxx`），填入 `.env`。

**Q：规划很慢？**
> Agent 调用 Qwen 大模型推理，6 个 Agent 串/并行执行，通常需要 30–90 秒。这是正常的，进度条会实时更新当前阶段。

**Q：只能规划成都？**
> 无 `GAODE_API_KEY` 时 MCP Server 使用 Mock 数据（仅成都）。配置高德 API 后支持全国所有城市。

**Q：地图不显示？**
> 检查 `.env` 中 `AMAP_JS_KEY` 是否填写。若已填写，检查高德控制台是否配置了 `localhost` 域名白名单。

**Q：分享链接打开后看不到地图？**
> 地图需要从当前服务的 `/api/travel/map-key` 获取 Key。分享链接只读模式同样会加载地图，需要服务在线。

**Q：`uv sync` 报错？**
> 确认 Python ≥ 3.11，然后运行 `pip install uv` 安装 uv，再重试。

**Q：如何接入真实携程/大众点评 API？**
> 打开对应 MCP Server 文件（`mcp_servers/ctrip.py` / `mcp_servers/dianping.py`），将 `_mock_*` 函数替换为真实 API 调用（httpx 请求），工具接口签名无需改变。

---

## 11. 变更记录

### v1.2.5 — 2026-05-13 | 智能路线规划 + 天气信息

**新增功能：**

1. **智能交通方式推荐**（每段路程自动判断）：
   - `< 1.5km` → 步行（绿色，估算步行分钟数）
   - `1.5–4km` → 骑行（蓝色，估算骑行分钟数）
   - `4–30km` → 查询高德 Transfer API：有地铁则显示「乘地铁」，无则「乘公交」
   - `> 30km` 或无公共交通 → 打车（黄色）

2. **实际道路路线渲染**：调用高德 Driving API 以实际道路路径替代直线折线，每天用不同颜色区分，路线按「酒店出发 → 各景点 → 返回酒店」规划

3. **天气组件**：地图左上角半透明卡片，显示：
   - 实时天气（温度/天气状况/风向风力/湿度）
   - 3 天预报（星期/天气图标/温度范围）
   - 数据来源：高德 `AMap.Weather` 插件（依赖 `AMAP_JS_KEY`）

**加载的 Amap 插件**（在 `_loadMap()` URL 中）：
`AMap.Polyline, AMap.Driving, AMap.Transfer, AMap.Walking, AMap.Cycling, AMap.Weather`

**关键方法：**
- `_fetchWeather(city)` — 获取实时天气 + 3 日预报
- `_planDayRoutes(structured, city)` — 对所有天异步规划路线
- `_resolveTransport(seg, city)` — 单段智能选择交通方式
- `_queryTransit(seg, city)` — 查询 Transfer API 是否有地铁
- `_renderActualRoute(waypoints, color)` — Driving API 获取道路路径并渲染
- `_updateDayCardRoute(dayNum, waypoints, modes)` — 更新日程卡片路线信息

**文件：** `static/app.js`, `static/styles.css`, `static/index.html`

---

### v1.2.4 — 2026-05-13 | 美食表格 + 地图标注全面升级

**新增：**
1. **美食推荐表格**：独立一栏可排序表格（#/餐厅/菜系/人均/招牌菜），点击行地图即跳转定位并弹出信息窗
2. **地图美食标注（常驻）**：橙色圆形叉子 SVG 图标，带序号颜色，点击弹出餐厅信息（菜系/价格/地址）
3. **地图酒店标注（常驻）**：蓝色圆形床铺 SVG 图标，点击弹出信息窗（星级/价格/地址）；点击酒店卡片地图跳转
4. **表格排序**：点击「价格排序」按钮切换升/降序，箭头实时反馈
5. **酒店卡片重设计**：星级用 SVG 金星替代 emoji，价格突出显示，点击高亮 + 地图跳转

**文件：**
- `static/app.js` — `_renderFoodTable()`、`_bindFoodTableEvents()`、`_addFoodMapMarkers()`、`_addHotelMapMarker()`
- `static/styles.css` — 食物表格、酒店卡片、区块标题全量重写

---

### v1.2.3 — 2026-05-13 | 规划体验全面优化

**改进：**

1. **景点数量**：每天 4-5 个景点（原每天 2 个，改为 `days × 5`）
2. **酒店选项**：全程入住单一酒店，展示 3 家选项供用户点选，地图随选择更新标注
3. **路线说明**：每天卡片显示「酒店出发 → 景点1 → 景点2 → … → 返回酒店」明确路线
4. **美食独立展示**：去掉每天卡片中的餐厅信息，改为底部独立「美食推荐」列表（10-15 家），附「在地图上显示」切换按钮
5. **地图增强**：景点标注改为带序号的彩色数字气泡，路线折线包含酒店出发/返回，美食标注可单独切换

**结构化数据变更（`structured_plan`）：**

| 字段 | 变化 |
|------|------|
| `hotel_options` | 新增，最多 3 家酒店供选择 |
| `selected_hotel` | 新增，默认选中第一家 |
| `days[].route_note` | 新增，当天路线文字说明 |
| `days[].attractions[].address` | 新增，景点地址 |
| `days[].attractions[].ticket_price` | 新增，门票参考价格 |
| `days[].meals` | 移除 |
| `days[].hotel` | 移除（改为顶部酒店选项区） |
| `foods` | 新增，平铺餐厅列表（替代原来按天分配） |

**涉及文件：**
- `app/agent/travel/attraction.py` — 景点数量 `days*5`
- `app/agent/travel/food.py` — 改为推荐 10-15 家餐厅的平铺列表
- `app/agent/travel/strategy.py` — `_build_structured_plan()` 全面重写
- `static/app.js` — `_showResult`/`_renderDayCard` 重写，新增酒店/美食区块、美食地图切换
- `static/styles.css` — 新增酒店选项卡、景点序号、美食列表样式

---

### v1.2.2 — 2026-05-13 | 高德地图 JS API 安全密钥支持

**修复：** 高德地图 JS API 2.0 要求在加载 SDK 前设置 `securityJsCode`，否则地图无法初始化。

- `app/config.py`：新增 `amap_js_security_code: str = ""`
- `.env`：新增 `AMAP_JS_SECURITY_CODE=`（在高德控制台 Key 详情页获取）
- `app/api/travel.py`：`/api/travel/map-key` 响应新增 `security_code` 字段
- `static/app.js`：`_loadMap()` 在加载 SDK 前注入 `window._AMapSecurityConfig = { securityJsCode }`

---

### v1.2.1 — 2026-05-13 | 前端旅游规划工作台全功能上线

**新增功能：**

1. **结构化表单输入**
   - 「旅游规划」Tab 切换后显示独立两栏布局
   - 表单字段：目的地 / 出发日期 / 天数 / 人数 / 预算 / 偏好标签 / 自然语言描述
   - 目的地为空时「开始规划」按钮禁用

2. **按天卡片可视化**
   - StrategyAgent 新增 `structured_plan` JSON 输出（从已有 state 数据组装，无额外 LLM 调用）
   - 每天一张卡片：景点（时长 + 小贴士）/ 餐饮（类型 + 价格）/ 住宿（价格）/ 当天费用
   - 卡片可展开/折叠，底部汇总总预算

3. **高德地图集成**
   - 前端通过 `/api/travel/map-key` 获取 JS Key（服务端下发，避免 Key 暴露）
   - 蓝色图钉标注景点，红色图钉标注酒店
   - 每天路线用不同颜色折线连接，地图自动缩放到全部标记范围
   - 点击景点/酒店图钉弹出信息窗口
   - 点击某天卡片高亮对应路线

4. **打印 PDF 导出**
   - 点击「打印 PDF」调用 `window.print()`
   - `@media print` CSS：隐藏侧边栏/工具栏/地图，卡片全宽展开

5. **持久化分享链接**
   - 后端 SQLite + SQLAlchemy 存储，重启不失效（`data/shares.db`）
   - `POST /api/travel/share` 生成唯一 UUID 链接
   - `GET /api/travel/share/{id}` 读取攻略数据
   - 分享链接只读模式：隐藏表单和工具栏

**涉及文件变更：**

| 文件 | 变更 |
|------|------|
| `app/agent/travel/state.py` | 新增 `structured_plan: Optional[dict]` |
| `app/agent/travel/strategy.py` | 新增 `_build_structured_plan()` |
| `app/agent/travel/attraction.py` | 提示词加 `lng`/`lat` 输出 |
| `app/agent/travel/hotel.py` | 提示词加 `lng`/`lat` 输出 |
| `app/services/travel_service.py` | complete 事件透传 `structured_plan` |
| `app/db/share_store.py` | 新建：SQLAlchemy share CRUD |
| `app/config.py` | 新增 `amap_js_key`、`share_db_url` |
| `app/models/travel.py` | 新增 `ShareRequest`、`ShareResponse` |
| `app/api/travel.py` | 新增 `/map-key`、`/share` POST/GET |
| `app/main.py` | lifespan 调用 `create_tables()` |
| `static/index.html` | 新增旅游两栏布局 + 分享弹窗 |
| `static/styles.css` | 新增旅游所有 CSS |
| `static/app.js` | 新增 `TravelUI` 类；更新 `switchAppMode` |
| `pyproject.toml` | 新增 `sqlalchemy>=2.0.0` |

---

### v1.0.0 — 2026-05-12 | 旅游多智能体后端上线

- 6 Agent 架构（Parser + Attraction + Route + Hotel + Food + Strategy）
- LangGraph Send() 实现并行（Route/Hotel/Food 同时执行）
- 3 个 MCP Server：高德（真实 API）+ 携程（Mock）+ 大众点评（Mock）
- 双语支持（zh/en），ParserAgent 自动检测
- MCP 失败 retry 2 次后降级 LLM 内置知识
- SSE 流式输出进度事件
