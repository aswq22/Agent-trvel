# 旅游规划前端全功能增强设计

**日期：** 2026-05-13  
**状态：** 已批准  
**关联：** [旅游 Agent 后端设计](2026-05-12-travel-agent-design.md)

---

## 背景与目标

现有旅游规划前端仅支持自然语言输入，输出为 Markdown 纯文本。本次增强在不破坏聊天功能的前提下，将「旅游规划」Tab 升级为完整的规划工作台，新增四项功能：

1. 结构化表单输入
2. 按天卡片可视化
3. 高德地图集成
4. 导出（打印 PDF）+ 分享链接

---

## 整体布局

切换到「旅游规划」Tab 时，`main-content` 区域替换为 `travel-layout`，聊天 DOM 隐藏但不销毁。切换回聊天时恢复。

```
sidebar（不变）  │  [工具栏: 打印 PDF | 生成分享链接]
                 │  ┌─── 左栏 50% ───┐  ┌─── 右栏 50% ───┐
                 │  │ 结构化表单      │  │  高德地图        │
                 │  │ 进度条          │  │ （景点/酒店标注）│
                 │  │ 按天卡片攻略    │  │                  │
                 │  └─────────────────┘  └──────────────────┘
```

分享链接只读模式（`/?share=<id>`）：隐藏表单、工具栏，仅展示卡片 + 地图。

---

## 结构化表单

字段直接映射后端 `TripParams`，无需修改后端接口：

| 字段 | 类型 | 默认值 | 必填 |
|------|------|--------|------|
| destination | text | — | ✓ |
| start_date | date | 今天 | — |
| days | number (1–14) | 3 | — |
| num_people | number (1–10) | 2 | — |
| budget | number | 3000 | — |
| preferences | 多选标签 | [] | — |
| user_input | textarea | — | — |

**发送逻辑：**
- 有 `user_input` → 以 `user_input` 为主，结构化字段填入 `trip_params` 作补充
- 无 `user_input` → 仅发 `trip_params`
- `destination` 为空时禁用提交按钮

---

## 后端变更：structured_plan

`strategy_agent` 额外输出 `structured_plan` 字段（JSON），与 `final_plan`（Markdown）并存：

```python
# app/agent/travel/state.py 新增字段
structured_plan: Optional[dict]  # {days, total_cost, tips}
```

`structured_plan` 结构：

```json
{
  "days": [
    {
      "day": 1,
      "date": "2026-05-20",
      "attractions": [
        {"name": "宽窄巷子", "duration": "2h", "tip": "避开午间人流", "lng": 104.06, "lat": 30.67}
      ],
      "hotel": {"name": "锦江宾馆", "price_per_night": 380, "lng": 104.08, "lat": 30.65},
      "meals": [
        {"type": "午餐", "name": "陈麻婆豆腐", "price": 60}
      ],
      "estimated_cost": 680
    }
  ],
  "total_cost": 2040,
  "tips": ["提前订票", "准备雨具"]
}
```

`TravelService._format_event` 在 `strategy_agent` 阶段同时透传 `structured_plan` 到 SSE `complete` 事件。

坐标来源：`attraction_agent` / `hotel_agent` 已从高德 MCP 获取 `lng/lat`，存入 state，`strategy_agent` 整合进 `structured_plan`。若坐标缺失则该条目跳过地图标注。

---

## 按天卡片 UI

每天一张卡片，点击卡片头部可展开/折叠：

```
┌──────────────────────────────────────────┐
│ 📅 第 1 天 · 5月20日            ¥680 ▼  │
├──────────────────────────────────────────┤
│ 🏛️ 景点                                 │
│   · 宽窄巷子  2h  💡避开午间人流         │
│   · 锦里古街  1.5h                      │
├──────────────────────────────────────────┤
│ 🍜 餐饮  午餐·陈麻婆豆腐 ¥60           │
├──────────────────────────────────────────┤
│ 🏨 住宿  锦江宾馆 ¥380/晚              │
└──────────────────────────────────────────┘
```

卡片列表底部：**总费用 ¥2040 / 3天 · 2人**

点击某天卡片 → 地图高亮该天路线，其余天路线变淡。

---

## 高德地图集成

### API Key 安全

Key 存于后端 `.env`（`AMAP_JS_KEY`），前端通过 `GET /api/travel/map-key` 获取，避免硬编码在 JS 中。

### 地图加载

```javascript
// 动态加载 Amap JS SDK（仅切换到旅游 Tab 时执行一次）
const script = document.createElement('script');
script.src = `https://webapi.amap.com/maps?v=2.0&key=${key}`;
```

### 标记与路线

| 事件 | 操作 |
|------|------|
| `progress.stage == "attractions"` | 批量添加景点标记（蓝色） |
| `progress.stage == "hotels"` | 添加酒店标记（橙色） |
| `complete` | 按天绘制折线（每天不同颜色），`fitBounds` 到全部标记 |

点击标记 → 信息窗口显示名称、简介、所属第几天。

---

## 分享功能

### 后端接口

```
POST /api/travel/share
  Body: { "plan": "<markdown>", "structured_plan": {...} }
  Response: { "share_id": "uuid", "url": "http://host/?share=uuid" }

GET  /api/travel/share/{share_id}
  Response: { "plan": "...", "structured_plan": {...} }
```

存储：**SQLite + SQLAlchemy**，持久化到 `data/shares.db`，重启后链接仍有效。SQLAlchemy 已作为传递依赖存在，无需新增安装。

表结构（`share_plans`）：

| 列 | 类型 | 说明 |
|----|------|------|
| id | VARCHAR(36) PK | UUID4 |
| plan | TEXT | Markdown 攻略 |
| structured_plan | TEXT | JSON 字符串 |
| created_at | DATETIME | 创建时间 |

启动时自动 `create_all`，`data/` 目录不存在时自动创建。

### 前端行为

- 点击「生成分享链接」→ 调用 POST 接口 → 弹出浮层显示链接 + 复制按钮
- 页面加载时检测 `?share=<id>` → 调用 GET 接口 → 切换到旅游 Tab，只读渲染卡片 + 地图，隐藏表单和工具栏

---

## 导出（打印 PDF）

纯前端，`window.print()` + `@media print` CSS：

```css
@media print {
  .sidebar, .travel-toolbar, .travel-form, .map-panel { display: none; }
  .day-cards { width: 100%; }
}
```

---

## 进度条

规划过程中，左栏表单区域替换为进度指示器（原有进度逻辑保留，样式增强）：

```
✅ 解析旅行参数
✅ 搜索景点
⏳ 规划路线（转圈动画）
⬜ 搜索酒店
⬜ 推荐美食
⬜ 生成攻略
```

完成后进度条收起，卡片区域展开。

---

## 文件变更清单

| 文件 | 变更类型 |
|------|----------|
| `app/agent/travel/state.py` | 新增 `structured_plan: Optional[dict]` |
| `app/agent/travel/strategy.py` | 输出 `structured_plan` JSON |
| `app/agent/travel/attraction.py` | state 中保留 `lng/lat` |
| `app/agent/travel/hotel.py` | state 中保留 `lng/lat` |
| `app/services/travel_service.py` | `complete` 事件透传 `structured_plan` |
| `app/db/share_store.py` | 新增 SQLAlchemy 模型 + CRUD（SQLite） |
| `app/api/travel.py` | 新增 `/share` POST/GET、`/map-key` GET |
| `app/models/travel.py` | 新增 `ShareRequest` / `ShareResponse` |
| `.env` | 新增 `AMAP_JS_KEY` |
| `app/config.py` | 新增 `amap_js_key`、`share_db_url` 配置项 |
| `static/index.html` | 新增 travel-layout 两栏 HTML 结构 |
| `static/app.js` | 重写旅游模式逻辑（表单/卡片/地图/分享） |
| `static/styles.css` | 新增旅游布局、卡片、地图、打印样式 |

---

## 不在本次范围内

- 实时协作编辑
- 多语言切换（en/zh 已由 ParserAgent 处理，前端不额外处理）
- 移动端响应式（桌面优先）
