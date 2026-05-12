# 旅游 Agent 系统设计文档

**日期：** 2026-05-12  
**项目：** super_biz_agent → 旅游多智能体系统  
**定位：** 多智能体架构演示项目

---

## 1. 项目概述

将现有 AIOps 智能运维系统重构为旅游规划多智能体系统。系统由 6 个协作 Agent 组成，能够根据用户的旅行需求自动完成景点推荐、路线规划、酒店筛选、美食推荐，并生成完整的逐日游玩攻略。

**核心目标：** 展示基于 LangGraph 子图嵌套的多智能体协作架构能力。

---

## 2. 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| Web 框架 | FastAPI + uvicorn | 复用现有 |
| Agent 编排 | LangGraph（子图嵌套） | 核心架构 |
| LLM | Qwen / QwQ（DashScope） | 复用现有 llm_factory |
| 工具集成 | MCP（Model Context Protocol） | 复用现有 mcp_client |
| 外部 API | 高德地图 / 携程 / 大众点评 | 通过 MCP Server 接入 |
| 输出方式 | SSE（Server-Sent Events）流式 | 复用现有 SSE 基础设施 |

---

## 3. 系统架构

### 3.1 整体数据流

```
用户输入（自然语言 或 结构化表单）
        ↓
[ParserAgent] — 提取结构化旅行参数（TripParams）
        ↓ 阶段 1
[AttractionAgent 子图] — 确定推荐景点列表
        ↓ Send() 并行分发，阶段 2
┌─────────────────────────────────────┐
│  [RouteAgent]  [HotelAgent]  [FoodAgent]  ← 并行执行
└─────────────────────────────────────┘
        ↓ 汇总所有结果，阶段 3
[StrategyAgent 子图] — 综合生成完整攻略
        ↓ SSE 流式推送
用户接收完整逐日旅游攻略
```

### 3.2 Agent 分工

| Agent | 类型 | 数据源 | 输出 |
|-------|------|--------|------|
| ParserAgent | 主图节点（无工具） | LLM 解析 | TripParams |
| AttractionAgent | 子图 | 大众点评 + 高德 POI | List[Attraction] |
| RouteAgent | 子图 | 高德路线规划 API | RouteInfo（按天） |
| HotelAgent | 子图 | 携程酒店搜索 API | List[Hotel] |
| FoodAgent | 子图 | 大众点评餐厅搜索 | List[Restaurant] |
| StrategyAgent | 子图（无工具） | 全部 State | final_plan（流式） |

### 3.3 执行阶段

- **阶段 1（串行）：** ParserAgent → AttractionAgent。景点是后续所有 Agent 的前提，必须先确定。
- **阶段 2（并行）：** RouteAgent / HotelAgent / FoodAgent 同时执行，均以 attractions 作为输入依据。
- **阶段 3（汇总）：** StrategyAgent 读取完整 State，流式生成完整攻略。

---

## 4. 数据模型

### 4.1 TripParams（ParserAgent 输出）

```python
class TripParams(BaseModel):
    destination: str           # 目的地，如"成都"
    start_date: str            # 出发日期，如"2026-06-01"
    days: int                  # 出行天数
    num_people: int            # 出行人数
    budget: float              # 总预算（元）
    preferences: List[str]     # 偏好标签，如["历史文化", "美食", "亲子"]
```

### 4.2 TravelPlanState（主图共享状态）

```python
class TravelPlanState(TypedDict):
    user_input: str                        # 原始用户输入
    trip_params: TripParams                # 解析后的结构化参数
    attractions: List[dict]                # AttractionAgent 输出
    route: dict                            # RouteAgent 输出
    hotels: List[dict]                     # HotelAgent 输出
    foods: List[dict]                      # FoodAgent 输出
    final_plan: str                        # StrategyAgent 输出（流式累积）
    messages: Annotated[List, add_messages] # 对话历史
    errors: dict                           # 各 Agent 错误信息（降级用）
```

---

## 5. 子图内部结构

每个 Agent 子图遵循统一模式：

```
[子图入口] → tool_node（MCP 工具调用）→ llm_node（Qwen 推理）→ output_node（结构化写回 State）
```

### 5.1 各子图工具配置

**AttractionAgent：**
- `gaode_poi_search`：高德 POI 搜索（景点名称、地址、评分）
- `dianping_attraction_search`：大众点评景点搜索（评分、评论、票价）

**RouteAgent：**
- `gaode_route_plan`：高德驾车/步行/公交路线规划
- `gaode_distance_matrix`：多点距离矩阵（优化景点访问顺序）

**HotelAgent：**
- `ctrip_hotel_search`：携程酒店搜索（按区域、价格、星级）
- `ctrip_hotel_detail`：酒店详情（房型、设施、评价）

**FoodAgent：**
- `dianping_restaurant_search`：大众点评餐厅搜索（按菜系、价位、位置）
- `dianping_menu`：餐厅菜单和招牌菜

---

## 6. 用户输入与 API

### 6.1 输入方式

支持两种输入方式，ParserAgent 统一处理：

- **自然语言：** `"帮我规划一个五天四夜的成都之旅，预算5000元，喜欢吃辣"`
- **结构化表单：** 直接传入 TripParams 字段

### 6.2 API 接口

```
POST /api/travel/plan
Content-Type: application/json
Accept: text/event-stream

Request:
{
  "user_input": "...",       // 自然语言输入（与 trip_params 二选一）
  "trip_params": { ... }     // 结构化参数（可选，优先级高于 user_input）
}

Response: SSE 流式推送
data: {"type": "progress", "agent": "attraction", "content": "..."}
data: {"type": "progress", "agent": "route", "content": "..."}
data: {"type": "final", "content": "完整攻略文本..."}
data: {"type": "done"}
```

---

## 7. 错误处理

| 场景 | 处理策略 |
|------|----------|
| MCP 工具调用失败 | 子图内 retry 2次；仍失败则 LLM 使用内置知识降级回答，不中断主流程 |
| 并行子图失败 | 将错误信息写入 `errors` 字段，StrategyAgent 在攻略中标注"该部分暂不可用" |
| ParserAgent 解析失败 | 返回默认 TripParams（空字段），通过 SSE 提示用户补充必要信息 |
| StrategyAgent 失败 | 直接将各子图原始结果拼接后返回，保证用户有基础信息可用 |

---

## 8. 目录结构变更

```
app/
├── config.py                  ✅ 保留
├── main.py                    ✅ 保留（路由挂载微调）
├── core/
│   ├── llm_factory.py         ✅ 保留
│   └── milvus_client.py       ✅ 保留（可选，旅游知识库）
├── agent/
│   ├── aiops/                 🔄 替换为 travel/
│   ├── travel/                ➕ 新目录
│   │   ├── __init__.py
│   │   ├── state.py           ➕ TravelPlanState, TripParams
│   │   ├── graph.py           ➕ 主编排图（三阶段流程）
│   │   ├── parser.py          ➕ ParserAgent（主图节点）
│   │   ├── attraction.py      ➕ AttractionAgent 子图
│   │   ├── route.py           ➕ RouteAgent 子图
│   │   ├── hotel.py           ➕ HotelAgent 子图
│   │   ├── food.py            ➕ FoodAgent 子图
│   │   └── strategy.py        ➕ StrategyAgent 子图
│   └── mcp_client.py          ✅ 保留
├── api/
│   ├── aiops.py               🔄 替换为 travel.py
│   ├── travel.py              ➕ POST /api/travel/plan（SSE）
│   ├── chat.py                ✅ 保留
│   ├── file.py                ✅ 保留
│   └── health.py              ✅ 保留
├── models/
│   ├── aiops.py               🔄 替换为 travel.py（TripRequest, TravelResponse）
│   └── request/response.py    ✅ 保留
└── services/
    ├── aiops_service.py       🔄 替换为 travel_service.py
    └── rag/vector 相关         ✅ 保留（可复用做旅游知识库）

mcp_servers/
├── （现有服务）
├── gaode_maps.py              ➕ 高德地图 MCP Server
├── ctrip.py                   ➕ 携程 MCP Server
└── dianping.py                ➕ 大众点评 MCP Server
```

---

## 9. 多语言支持

系统通过 ParserAgent 自动检测输入语言，整个攻略以相同语言输出。

| 项目 | 说明 |
|------|------|
| 支持语言 | 中文（简体）、英文；Qwen 原生支持，无需额外翻译层 |
| 语言检测 | ParserAgent 在解析 TripParams 时同时提取 `language` 字段（`"zh"` / `"en"`） |
| 传递方式 | `TripParams` 新增 `language: str` 字段，随 State 传递给所有子图 |
| 提示词适配 | 各子图提示词根据 `language` 字段动态切换中英文指令 |
| 输出语言 | StrategyAgent 以检测到的语言生成完整攻略 |

`TripParams` 更新为：

```python
class TripParams(BaseModel):
    destination: str
    start_date: str
    days: int
    num_people: int
    budget: float
    preferences: List[str]
    language: str = "zh"       # 自动检测，默认中文
```

---

## 10. 不在范围内（Out of Scope）

- 用户登录 / 账户系统
- 历史记录持久化
- 支付 / 预订功能
- 移动端适配
