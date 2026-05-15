# SuperBizAgent — 智能旅游助手 + 动态 RAG 知识库

> 基于 LangChain / LangGraph / FastAPI / Milvus 的多功能智能助手，支持：聊天对话、文档 RAG、**小红书动态知识库 RAG**、旅游多智能体规划、AIOps 故障诊断。

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.3+-00A1EA.svg)](https://milvus.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#许可证)

---

## 目录

- [一、功能概览](#一功能概览)
- [二、快速开始](#二快速开始)
- [三、功能详解](#三功能详解)
  - [3.1 普通对话](#31-普通对话快速--流式)
  - [3.2 文件 RAG](#32-文件-rag上传文档--自动索引)
  - [3.3 小红书动态 RAG ⭐](#33-小红书动态-rag-)
  - [3.4 旅游多智能体规划](#34-旅游多智能体规划)
  - [3.5 AIOps 故障诊断](#35-aiops-故障诊断)
- [四、技术栈](#四技术栈)
- [五、系统架构](#五系统架构)
- [六、API 接口一览](#六api-接口一览)
- [七、.env 完整配置](#七env-完整配置)
- [八、自动化测试](#八自动化测试)
- [九、故障排查](#九故障排查)
- [十、已知限制与后续方向](#十已知限制与后续方向)

---

## 一、功能概览

项目有 **5 条相对独立的功能链路**，每条对应一个 API 命名空间与一组后台依赖。按需启动相应进程即可，不用全部一起跑。

| 编号 | 功能 | 主要 API | 必须的进程 |
|---|---|---|---|
| ① | 普通对话 | `/api/chat`、`/api/chat_stream` | 主服务 |
| ② | 文件 RAG | `/api/upload` + `/api/chat`* | 主服务 + Milvus |
| ③ | **小红书动态 RAG** | `/api/chat/rag`、`/api/chat/rag_stream`、`/api/xhs/*` | 主服务 + Milvus + xhs MCP |
| ④ | 旅游多智能体 | `/api/travel/plan` | 主服务 + 高德 / 携程 / 大众点评 MCP |
| ⑤ | AIOps | `/api/aiops` | 主服务 + cls / monitor MCP |

\*文件 RAG 通过文档 → 默认分区入库 → 与 LLM 共用 `/chat` 接口；不与小红书 RAG 冲突。

### 本次交付的核心功能：小红书动态 RAG

- 用户可以**按需**通过小红书 MCP 抓取真实笔记（关键词 + 城市）入库 Milvus
- **按城市分库**：同一个城市多次入库**追加**到同一个 Milvus partition，不重复造库
- 聊天时**自由选择**知识库：选定某城市 → 只检索该 partition；不选 → 跨所有小红书分区做全局检索
- LLM 回答时**自动展示引用来源**：可折叠卡片显示 N 条小红书攻略的标题、作者、点赞数、链接
- 数据流端到端：**MCP → 切块 → 本地 embedding → Milvus partition → 检索 → LLM → SSE 流式 + 引用**

---

## 二、快速开始

### 2.1 系统要求

| 组件 | 版本 / 备注 |
|---|---|
| 操作系统 | Windows 11 / macOS / Linux（本文以 Windows + PowerShell 为准） |
| Python | **3.13**（项目 `.python-version` 固定；3.10 不兼容） |
| Docker Desktop | 用于跑 Milvus |
| 包管理器 | `uv`（推荐，比 pip 快 10×）：`pip install uv` |
| DeepSeek API Key | 推荐，便宜——用于 LLM 调用 |
| DashScope API Key | 可选，仅当用云端 embedding 时；本期项目默认走本地 embedding **不依赖** DashScope |
| 高德 Web 服务 Key | 仅用旅游 Agent 时必需 |

### 2.2 安装

```powershell
git clone <repo>
cd super_biz_agent

# 用 uv 创建并装依赖（最快）
uv venv
.venv\Scripts\activate
uv pip install -e .

# 首次启动会从 HuggingFace 下载本地 embedding 模型
# (BAAI/bge-small-zh-v1.5，约 100MB，缓存到 ~/.cache/huggingface)
```

### 2.3 配置 `.env`

新建 `.env`（参照本文末尾的「[七、.env 完整配置](#七env-完整配置)」一节）。**最小配置**只需 `DEEPSEEK_API_KEY`。

### 2.4 三窗口最小启动（演示小红书 RAG）

按顺序开 3 个 PowerShell 窗口，每个都先 `.venv\Scripts\activate`：

```powershell
# 窗口 1 — Milvus 向量数据库
docker compose -f vector-database.yml up -d

# 窗口 2 — 小红书 MCP（端口 8013）
python mcp_servers/xhs_server.py

# 窗口 3 — FastAPI 主服务（端口 9900）
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
```

成功标志（窗口 3）：

```
SuperBizAgent v1.0.0 启动中...
监听地址: http://0.0.0.0:9900
加载本地 embedding 模型: BAAI/bge-small-zh-v1.5
本地 Embeddings 初始化完成 — 维度: 512
成功连接到 Milvus
collection 'biz' 已加载
```

访问：

- **Web 界面**：http://localhost:9900
- **Swagger API 文档**：http://localhost:9900/docs

### 2.5 端到端冒烟测试

新开第 4 个窗口（不用激活 venv，curl 是 Windows 自带的）：

```powershell
# 1. 入库一个城市的笔记
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'

# 期望返回（首次 ~10s，因为 Playwright 启 chromium）:
# {"code":200, "data":{"kb_name":"xhs_xxxxxxxx","ingested":5,"chunks":5,...}}

# 2. 列出所有知识库
curl.exe http://localhost:9900/api/xhs/kb/list

# 3. 基于该 KB 做 RAG 对话（流式）
curl.exe -N -X POST http://localhost:9900/api/chat/rag_stream `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"成都必吃美食\",\"session_id\":\"smoke-1\",\"kb_name\":\"xhs_xxxxxxxx\"}'
```

或者打开 http://localhost:9900 在浏览器里：
1. 输入框右下角下拉切到「**RAG · 小红书**」
2. 输入框上方出现淡橙色 KB bar
3. 点 KB bar → 抽屉滑出 → 选「成都」KB
4. 提问 → 看助手回答顶部出现可展开的「📕 基于 N 条小红书攻略」

---

## 三、功能详解

### 3.1 普通对话（快速 / 流式）

- **快速模式** `/api/chat`：阻塞返回完整答案
- **流式模式** `/api/chat_stream`：SSE 逐字推送
- 共享会话历史（同一 `session_id` 在所有聊天接口之间历史连续）
- LLM 默认走 DeepSeek（`deepseek-chat`），fallback DashScope（`qwen-max`）

```bash
curl -X POST http://localhost:9900/api/chat \
  -H "Content-Type: application/json" \
  -d '{"Question":"你好","session_id":"u-001"}'
```

### 3.2 文件 RAG（上传文档 + 自动索引）

- 端点：`POST /api/upload`（multipart form，字段 `file`）
- 支持 `.md` / `.txt` / `.pdf` / `.docx`，自动切块（chunk_max_size=800，overlap=100）并入库到 Milvus 的 **`_default` 分区**
- 与 XHS RAG 的 `xhs_*` 分区**完全隔离**
- 上传后在 `/api/chat` 提问时系统不会自动检索——这条链路目前是"上传后的数据 + 主动调用 knowledge_tool" 的工作流，主要给 Agent 用（不是给普通聊天）

### 3.3 小红书动态 RAG ⭐

本次交付的核心。完整数据流：

```
┌──────────────────── 入库链路（按需触发）─────────────────────┐
│                                                              │
│  前端「搜索并入库」表单 / curl POST /api/xhs/ingest/mcp     │
│      │                                                       │
│      │  { keyword, city, count }                             │
│      ▼                                                       │
│  xhs_ingestion_service                                       │
│    1. kb_name = "xhs_<md5(city)前8位>"  (按 city 分库)       │
│    2. 调 fastmcp Client → xhs_server (8013)                  │
│      └── xhs_server 用 Playwright 启 chromium                │
│          打开 search_result?keyword=城市+关键词              │
│          解析 DOM 抽笔记列表（title / author / likes）       │
│    3. 切块（RecursiveCharacterTextSplitter）                 │
│    4. 本地 embedding (BAAI/bge-small-zh-v1.5)                │
│    5. pymilvus collection.insert(partition_name=kb_name)     │
│      └── 同 city 重复入库 = 追加到同一 partition             │
│                                                              │
│  ← 返回 { kb_name, ingested, chunks, keyword, city }         │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────── 对话链路 ────────────────────────────────┐
│                                                              │
│  前端 RAG 子模式 / curl POST /api/chat/rag_stream            │
│      │  { Question, session_id, kb_name? }                   │
│      ▼                                                       │
│  rag_service.build_rag_context                               │
│    ├─ kb_name 给定                                            │
│    │     → similarity_search_in_partition(query, kb_name, k) │
│    └─ kb_name 空 / null                                       │
│          → similarity_search_across_kb_partitions(query, k)  │
│            （仅跨 xhs_* 分区，不污染 _default）              │
│                                                              │
│  ↓ 命中 docs                                                  │
│  citations 按 note_id 去重                                   │
│  构造 messages = [SystemPrompt + 参考资料块,                 │
│                    ...session_history[-20:],                 │
│                    HumanMessage(Question)]                   │
│                                                              │
│  ↓                                                            │
│  LLMFactory.create_travel_llm(streaming=True).astream        │
│                                                              │
│  ↓ SSE 事件                                                   │
│  event: citations  (先推, 引用先到)                          │
│  event: content    (逐 chunk)                                │
│  ...                                                         │
│  event: done                                                 │
│                                                              │
└──────────────────────────────────────────────────────────────┘

┌──────────────────── 管理链路 ────────────────────────────────┐
│  GET    /api/xhs/kb/list           → 列出所有 xhs_* 分区     │
│  DELETE /api/xhs/kb/{kb_name}      → 释放 + drop_partition   │
└──────────────────────────────────────────────────────────────┘
```

**KB 命名规则**：`xhs_<md5(city.strip())前8位>`，例如：
- `成都` → `xhs_a3f9c1b2`
- `北京` → `xhs_8d4e2f01`
- 城市留空 → 固定常量 `xhs_global`（手动入库等场景的兜底）

`description` 字段存城市名（"成都"），前端 KB 卡片直接展示。

**前端 UI 关键点**：

- 聊天输入框右下角子模式下拉新增「**RAG · 小红书**」
- 选中后输入框上方出现淡橙色 **KB 选择条**：`📕 知识库: [当前 KB ▾] [+ 管理]`
- 默认显示「🌐 全部知识库」表示跨分区检索
- 点 KB 选择条任意位置 → 右侧 420px 抽屉滑出
  - 上半部：**搜索并入库**表单（关键词 + 城市 + 数量）
  - 下半部：**我的知识库**列表，每张卡片有删除按钮（点击 → inline 两步确认 → DELETE）
  - 第一张卡片固定是「🌐 全部知识库」用来取消选择
- 助手消息气泡里若有引用：消息**最上方**出现可折叠的 `<details>`：
  ```
  ▶ 📕 基于 3 条小红书攻略
  ```
  展开后是带链接的笔记列表：`[1] 标题 · 作者 · 8832 赞`

**会话连续性**：同一 `session_id` 在 `/chat`、`/chat_stream`、`/chat/rag`、`/chat/rag_stream` 之间共享历史（后端有共享的 `session_store`）。RAG 一轮 → 切回普通聊天追问"那门票呢" → 也能基于上一轮上下文回答。

### 3.4 旅游多智能体规划

LangGraph 子图嵌套架构的 demo。6 个 Agent 协作：

```
ParserAgent  → 解析"成都 3 日游 预算 3000"为结构化 trip
   ↓
   ├─→ AttractionAgent  (高德 POI 查景点)
   ├─→ RouteAgent       (高德 driving 路线规划)
   ├─→ HotelAgent       (携程 mock)
   └─→ FoodAgent        (大众点评 mock)
   ↓  ← 三路并行，结果汇总
StrategyAgent → 综合输出 final_plan + structured_plan
```

端点 `POST /api/travel/plan`，SSE 流式返回每个 Agent 的中间事件。

### 3.5 AIOps 故障诊断

Plan-Execute-Replan 模式的自动诊断系统：

```
Planner → 4-6 步诊断计划
Executor → 调用 cls / monitor MCP 工具
Replanner → 评估结果，决定继续 / 调整 / 收尾
→ 输出根因分析 + 运维建议（流式）
```

端点 `POST /api/aiops`。

---

## 四、技术栈

### 4.1 整体选型概览

| 层 | 技术 | 选型理由 |
|---|---|---|
| Web 框架 | **FastAPI** + SSE-Starlette | 异步、auto-docs、SSE 一等公民 |
| LLM 编排 | **LangChain** + **LangGraph** | 链/Agent/图 状态管理；多 Agent 协作 |
| LLM 推理 | **DeepSeek** (`deepseek-chat`) + DashScope fallback | DeepSeek 中文好且便宜；不放鸡蛋一篮子 |
| 向量数据库 | **Milvus 2.3+** | 单机版 docker 跑得起、Partition 原生隔离 |
| Embedding | **本地 BAAI/bge-small-zh-v1.5**（sentence-transformers） | 512 维，~100MB，**0 元运行**，中文质量好 |
| MCP 协议 | **fastmcp** | 把工具拆成独立进程，热插拔 |
| XHS 抓取 | **Playwright** (headless Chromium) | 避开 X-S 签名逆向；DOM 解析比 JSON 接口稳 |
| 前端 | 纯 Vanilla JS + CDN（marked、highlight.js） | 项目要求零构建工具链 |
| 测试 | **pytest** + pytest-asyncio + unittest.mock | 标准组合，77 单元测试 |

### 4.2 关键架构决策（XHS RAG）

| 决策 | 我们选 | 拒掉的方案 |
|---|---|---|
| 多 KB 隔离 | Milvus 原生 Partition | metadata 字段过滤（慢、删除麻烦）；多 collection（资源浪费） |
| Embedding | 本地 bge-small-zh-v1.5 | DashScope（按调用收费）；OpenAI embeddings（要 key） |
| LLM 是否自动触发 RAG | 用户**手动**选 KB | LLM tool calling 决定（不可控、token 浪费） |
| KB 粒度 | 按 city（同 city 多次入库追加） | 每次搜索独立 KB（很快泛滥成 50+ 个） |
| XHS 数据 | Playwright 抓 DOM | 逆向 X-S 签名调内部 API（易碎，每月坏一次） |
| 引用展示 | 消息顶部可折叠 | 消息底部 footnote（要 LLM 配合，不可靠） |
| 命中 0 条时 | 仍走 LLM，prompt 改写"通用建议" | 返 404 错误（用户体验差） |

---

## 五、系统架构

### 5.1 目录结构

```
super_biz_agent/
├── app/
│   ├── main.py                          # FastAPI 入口 + lifespan
│   ├── config.py                        # pydantic-settings 配置加载
│   ├── api/
│   │   ├── chat.py                      # /api/chat、/chat_stream         ① 普通对话
│   │   ├── chat_rag.py                  # /api/chat/rag、/chat/rag_stream  ③ XHS RAG 对话
│   │   ├── xhs.py                       # /api/xhs/ingest、/kb/list、/kb/{n}  ③ XHS KB 管理
│   │   ├── travel.py                    # /api/travel/plan                 ④ 旅游 Agent
│   │   ├── aiops.py                     # /api/aiops                       ⑤ AIOps
│   │   ├── file.py                      # /api/upload                      ② 文件 RAG
│   │   └── health.py                    # /health
│   ├── agent/
│   │   ├── travel/                      # 6 个旅游 Agent（parser/attraction/route/hotel/food/strategy）
│   │   ├── aiops/                       # Plan-Execute-Replan
│   │   └── mcp_client.py                # 通用 MCP 客户端封装
│   ├── services/
│   │   ├── rag_service.py               # build_rag_context — 检索 + prompt + citations 去重
│   │   ├── session_store.py             # 跨 endpoint 共享聊天会话
│   │   ├── vector_store_manager.py      # Milvus 入库/检索 + 5 个 partition 方法
│   │   ├── vector_embedding_service.py  # 本地 bge embedding 单例
│   │   ├── xhs_ingestion_service.py     # XHS MCP 调用 → 入 partition 管道
│   │   └── travel_service.py            # 旅游 Agent 编排
│   ├── core/
│   │   ├── llm_factory.py               # DeepSeek/DashScope 工厂
│   │   └── milvus_client.py             # biz collection 单例 (512 维)
│   ├── models/                          # pydantic 数据模型
│   └── utils/logger.py                  # loguru 配置
├── mcp_servers/
│   ├── xhs_server.py                    # 小红书 MCP — Playwright 抓取（端口 8013）   ③
│   ├── gaode_maps.py                    # 高德 MCP                   （端口 8010）  ④
│   ├── ctrip.py                         # 携程 mock                   （端口 8011） ④
│   ├── dianping.py                      # 大众点评 mock               （端口 8012） ④
│   ├── cls_server.py                    # CLS 日志 mock              （端口 8003）  ⑤
│   └── monitor_server.py                # 监控数据 mock              （端口 8004）  ⑤
├── static/
│   ├── index.html                       # 单页前端
│   ├── app.js                           # ~2200 行 vanilla JS（含 XHS RAG 全部交互）
│   └── styles.css                       # ~2470 行 CSS
├── tests/
│   ├── api/                             # API 层测试
│   └── services/                        # 服务层单元 + 集成测试
├── docs/
│   └── superpowers/
│       ├── specs/                       # 设计文档
│       └── plans/                       # 实施计划
├── vector-database.yml                  # Milvus docker-compose
├── pyproject.toml                       # 依赖
├── .env                                 # 配置（需自建）
├── README.md                            # 原始 README（旧版 AIOps 项目）
├── FULL_README.md                       # 5 条链路通用启动指南
└── README_Final.md                      # 👉 本文档（最终版）
```

### 5.2 模块依赖关系（XHS RAG 链路）

```
                       前端 (static/app.js)
                          │
                          ▼ HTTP/SSE
              ┌──────────────────────────────┐
              │  FastAPI 主服务 (uvicorn)    │
              │  app/main.py                 │
              └──────────────────────────────┘
                          │
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                      ▼
   app/api/xhs.py    app/api/chat_rag.py    app/api/chat.py
        │                 │                      │
        ▼                 ▼                      ▼
 xhs_ingestion_  rag_service.py           session_store
 service.py            │
        │              ▼
        │       vector_store_manager.py ─── pymilvus ──→ Milvus
        │              │
        │              └── vector_embedding_service.py
        │                            │
        │                  sentence-transformers
        │                  (本地 BAAI/bge-small-zh-v1.5)
        │
        ▼ fastmcp Client
   ┌────────────────────────────┐
   │ xhs_server.py (独立进程)   │
   │ 端口 8013                  │
   │ Playwright headless        │
   │ chromium → DOM 解析        │
   └────────────────────────────┘
```

---

## 六、API 接口一览

完整列表见 http://localhost:9900/docs（Swagger UI）。下表是核心端点：

### 6.1 普通对话

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 阻塞对话 |
| POST | `/api/chat_stream` | SSE 流式对话 |
| GET | `/api/chat/session/{session_id}` | 拿会话历史 |
| POST | `/api/chat/clear` | 清空指定会话 |

### 6.2 小红书 RAG

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/xhs/ingest/mcp` | 调 XHS MCP 搜索 + 入 partition |
| POST | `/api/xhs/ingest/text` | 手动粘贴笔记入库 |
| GET | `/api/xhs/kb/list` | 列出所有 `xhs_*` 分区 |
| DELETE | `/api/xhs/kb/{kb_name}` | 删除指定分区 |
| GET | `/api/xhs/stats` | biz collection 总向量数 |
| POST | `/api/chat/rag` | RAG 阻塞对话 |
| POST | `/api/chat/rag_stream` | RAG 流式（首事件 = citations，然后 content，最后 done） |

#### `/api/chat/rag_stream` 请求体

```jsonc
{
  "Question":   "成都必吃美食推荐",
  "session_id": "u-001",
  "kb_name":    "xhs_a3f9c1b2",   // 可选；空 → 跨所有 xhs_* 分区
  "top_k":      3                  // 可选，默认 config.rag_top_k=3
}
```

#### SSE 事件协议

```
data: {"type":"citations","data":[{"title":"成都5日游","url":"...","author":"...","likes":8832}, ...]}

data: {"type":"content","data":"根据小红书"}

data: {"type":"content","data":"攻略，建议..."}

data: {"type":"done"}
```

异常：

```
data: {"type":"error","data":"知识库 'xhs_xxx' 不存在"}
```

### 6.3 旅游多智能体

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/travel/plan` | SSE 流式规划，输出 6 Agent 中间事件 + final_plan |
| GET | `/api/travel/map-key` | 返回前端用的高德 JS API key |
| POST | `/api/travel/share` | 生成攻略分享链接 |
| GET | `/api/travel/share/{id}` | 查看分享攻略 |

### 6.4 AIOps

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/aiops` | SSE 流式诊断（Plan-Execute-Replan） |

### 6.5 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 主服务 + Milvus 连接状态 |

---

## 七、.env 完整配置

新建 `.env` 在项目根目录。**最小必填只有 LLM key**（DeepSeek 或 DashScope 二选一）。其余按需。

```ini
# ── 应用 ─────────────────────────────────────────────
APP_NAME=SuperBizAgent
DEBUG=True
HOST=0.0.0.0
PORT=9900

# ── LLM ─────────────────────────────────────────────
# 普通聊天 / 旅游 Agent / RAG 对话 优先 DeepSeek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# DashScope 作为 fallback；AIOps 也用 qwen-max
# 注：本期 embedding 已切到本地，DashScope 仅在 LLM fallback 时用，账户欠费不影响 RAG
DASHSCOPE_API_KEY=
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-max
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4   # 已弃用（本地 embedding 优先）

# ── Milvus 向量库 ───────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_TIMEOUT=10000

# ── RAG ─────────────────────────────────────────────
RAG_TOP_K=3
RAG_MODEL=qwen-max
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100

# ── 小红书 MCP / RAG（功能 ③）──────────────────────
MCP_XHS_URL=http://localhost:8013/mcp
# Playwright 需要的 cookie（浏览器登录小红书后从 F12 拷贝）
# 不填则 Playwright 启 headless chromium 时未登录，可能拿不到结果
XHS_COOKIE=

# ── 旅游 Agent MCP（功能 ④）─────────────────────────
MCP_GAODE_URL=http://localhost:8010/mcp
MCP_CTRIP_URL=http://localhost:8011/mcp
MCP_DIANPING_URL=http://localhost:8012/mcp
GAODE_API_KEY=                # https://lbs.amap.com（Web 服务）
AMAP_JS_KEY=                  # 前端地图（Web JS API）
AMAP_JS_SECURITY_CODE=        # JS API 2.0 安全密钥

# ── AIOps MCP（功能 ⑤）─────────────────────────────
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp

# ── 分享数据库 ─────────────────────────────────────
SHARE_DB_URL=sqlite:///data/shares.db
```

---

## 八、自动化测试

```powershell
.venv\Scripts\activate

# 全量单元测试（不需要 Milvus / MCP，全 mock）
python -m pytest tests/ -v --no-cov
# → 77 passed, 4 skipped（集成测试默认跳过）

# Milvus 集成测试（需 Milvus 真实跑着 + 设置环境变量）
$env:RUN_MILVUS_TESTS="1"
python -m pytest tests/services/test_vector_store_partition_integration.py -v --no-cov
# → 4 passed

# 单独跑某个测试文件
python -m pytest tests/services/test_rag_service.py -v --no-cov

# 单独跑某个 case
python -m pytest tests/api/test_chat_rag_api.py::test_chat_rag_stream_emits_citations_then_content_then_done -v --no-cov
```

### 测试覆盖范围

| 模块 | 测试文件 | 覆盖点 |
|---|---|---|
| `session_store` | `tests/services/test_session_store.py` | get/append/clear 隔离 |
| Milvus partition | `tests/services/test_vector_store_manager_partition.py` | ensure/list/drop/insert/search（mock collection） |
| `xhs_ingestion` | `tests/services/test_xhs_ingestion_service.py` | `_make_kb_name` 确定性、0 笔记不创建分区 |
| `rag_service` | `tests/services/test_rag_service.py` | citations 去重、空命中 fallback、history 截 20 |
| `/api/xhs/*` | `tests/api/test_xhs_api.py` | ingest_mcp 返 kb_name、list、delete 404 |
| `/api/chat/rag*` | `tests/api/test_chat_rag_api.py` | happy path、KB not found、SSE 事件顺序 |
| Milvus 真集成 | `tests/services/test_vector_store_partition_integration.py` | partition 隔离、跨 partition 检索 |

---

## 九、故障排查

### 9.1 启动期

| 症状 | 原因 / 处理 |
|---|---|
| `Fail connecting to server on localhost:19530` | Milvus 没起：`docker ps` 检查；`docker compose -f vector-database.yml up -d` |
| 启动日志报 `RuntimeError: 向量维度不匹配` | 旧 collection 维度不是 512 —— 主服务**会自动 drop 重建**，等几秒重启就好 |
| 启动慢（30s+ 才打印 Embeddings 初始化完成） | 首次启动 sentence-transformers 在下模型（~100MB），后续启动会快 |
| `playwright._impl._errors.Error: Executable doesn't exist` | chromium 没装：`playwright install chromium` |

### 9.2 入库期（`/api/xhs/ingest/mcp`）

| 症状 | 原因 / 处理 |
|---|---|
| `{"code":500,"message":"MCP 连接失败: ..."}` | 窗口 2 的 `xhs_server.py` 没起或被占端口 |
| `{"code":200,"data":{"kb_name":null,"ingested":0}}` | Playwright 抓到了页面但没解析出笔记 → 看 `mcp_servers/xhs_debug.png` 与 `xhs_debug.html` 现场（登录页 / 验证码 / DOM 变了） |
| 入库非常慢（> 30s） | Playwright 冷启 chromium ~3s + XHS 页面加载 + 解析。后续请求复用 context 会快 |
| Cookie 失效（XHS 反爬） | 重新从浏览器 F12 拿 cookie，更新 `.env` 里 `XHS_COOKIE`，重启**窗口 2** |

### 9.3 对话期（`/api/chat/rag_stream`）

| 症状 | 原因 / 处理 |
|---|---|
| 助手回复 "以下为通用建议..." | 这条 query 没命中 KB 任何 chunk —— 设计行为，不是错。说明 query 与该 KB 主题无关 |
| 助手红字"知识库 'xxx' 不存在" | 该 KB 被删了；先 `GET /api/xhs/kb/list` 看真实分区名 |
| 助手红字"网络错误" | 主服务挂了 / 浏览器到主服务的 fetch 断了 |
| Citations 不显示 | LLM 命中 0 条引用源（设计行为）or 浏览器折叠条默认关闭 |

### 9.4 前端期

| 症状 | 排查 |
|---|---|
| 切到 RAG 子模式后 KB bar 不出现 | F12 → Console 看有无 JS 错；强刷 Ctrl-F5 拿最新 JS |
| 抽屉打开是空的 / 加载失败 | F12 → Network 看 `/api/xhs/kb/list` 返回什么 |
| KB 卡片显示乱码 | description 含特殊字符；正常 city 名不会有此问题 |

### 9.5 进程清理

Windows 上 PowerShell 关窗口有时不会 SIGINT 子进程，残留 Python 进程会占用 numpy / chromium DLL：

```powershell
# 看所有 Python 进程
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id,StartTime -AutoSize

# 强制终止指定进程
Stop-Process -Id <PID> -Force
```

或者重启 PowerShell。

---

## 十、已知限制与后续方向

### 10.1 已知限制

| 类别 | 描述 |
|---|---|
| XHS 笔记内容 | 列表页只拿到 title 当 content。完整正文需要再进每条详情页（每条多 5-10s 没做） |
| XHS 反爬 | Cookie 仍可能被风控；Playwright 不能过验证码 |
| Chromium 资源 | xhs_server 进程内常驻一个 chromium（约 ~200MB 内存） |
| Embedding 多语言 | bge-small-zh 是中文专用；英文/日文 query 质量会下降 |
| Milvus 单机 | 当前 docker-compose 是 standalone；KB > 100 个时考虑分布式部署 |
| 前端测试 | 没有 Jest/Vitest，靠手工 22 项 smoke test |
| localStorage 跨 tab | 多 tab 删除 KB 不会主动通知其他 tab |

### 10.2 后续可做

1. **进详情页拿正文**：在 xhs_server 加 `_fetch_note_detail`，列表拿 N 条 link 后并发 `page.goto` 抽 desc + 评论。粗算每条多 5s 但 RAG 引用质量大幅提升
2. **多语言 embedding**：换 `BAAI/bge-m3`（更大、多语言）—— 但模型 ~1.2GB，启动慢
3. **跨 tab 实时同步**：用 `localStorage` 的 `storage` 事件或 SSE 推送 KB 列表变更
4. **citations 点击侧栏预览**：点 citation 不是新 tab 跳转，而是在右侧侧栏显示笔记原文 + 图片
5. **RAG 质量评估面板**：对比"开/关 RAG"两种回答，做 A/B
6. **Milvus 索引调优**：当前是 IVF_FLAT/L2 + nprobe=16，可换 HNSW 提速

### 10.3 工程改进

- 抽 `claude-skill` 化的部分到独立 plugin 仓库
- 考虑用 LangSmith / Phoenix 加 trace
- 加 OpenAPI 客户端 codegen 给前端用，省去手写 fetch

---

## 许可证

MIT License — 见 `LICENSE`（如有）。

Author: chief
