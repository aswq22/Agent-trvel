# SuperBizAgent — 智能旅游助手 + 动态 RAG 知识库

> 基于 LangChain / LangGraph / FastAPI / Milvus 的多功能智能助手。当前阶段聚焦：**小红书动态 RAG 知识库** + **旅游多智能体规划**。

[![Python](https://img.shields.io/badge/Python-3.13+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-009688.svg)](https://fastapi.tiangolo.com/)
[![Milvus](https://img.shields.io/badge/Milvus-2.3+-00A1EA.svg)](https://milvus.io/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](#许可证)

---

## 目录

- [一、项目简介](#一项目简介)
- [二、技术栈](#二技术栈)
- [三、全链路跑通流程](#三全链路跑通流程)
- [四、功能详解](#四功能详解)
- [五、API 接口](#五api-接口)
- [六、.env 配置](#六env-配置)
- [七、测试用例](#七测试用例)
- [八、项目演进过程](#八项目演进过程)
- [九、系统架构](#九系统架构)
- [十、故障排查](#十故障排查)
- [十一、已知限制与后续方向](#十一已知限制与后续方向)
- [许可证](#许可证)

---

## 一、项目简介

SuperBizAgent 是一个支持多种 AI 助手功能的整合性项目，由 5 条相对独立的功能链路组成：

| 编号 | 功能 | 入口 API | 必须的进程 |
|---|---|---|---|
| ① | 普通对话 | `/api/chat`、`/api/chat_stream` | 主服务 |
| ② | 文件 RAG | `/api/upload` | 主服务 + Milvus |
| ③ | **小红书动态 RAG** ⭐ | `/api/chat/rag`、`/api/xhs/*` | 主服务 + Milvus + xhs MCP |
| ④ | 旅游多智能体 | `/api/travel/plan` | 主服务 + 高德/携程/大众点评 MCP |

按需启动对应进程即可，不用全部跑。

### 本项目最新交付（功能 ③）

**小红书动态 RAG** 端到端打通：

- 用户在前端「RAG · 小红书」子模式下，可**按需**抓取小红书旅游攻略入 Milvus
- **按城市分库**：同一城市多次入库会**追加**到同一 partition；不同城市分库存储
- 聊天时**自由选择**知识库：选某城市 → 在该 partition 检索；不选 → 跨所有 xhs 分区**全局检索**
- LLM 回答时自动展示**引用来源**：可折叠卡片显示笔记标题、作者、点赞数、链接
- 数据流：**Playwright MCP 抓取 → 切块 → 本地 embedding → Milvus partition → 检索 → SSE 流式 LLM**

---

## 二、技术栈

### 2.1 整体选型

| 层 | 技术 | 选型理由 |
|---|---|---|
| Web 框架 | **FastAPI 0.109+** + SSE-Starlette | 异步、auto OpenAPI 文档、SSE 一等公民 |
| LLM 编排 | **LangChain 0.1+** + **LangGraph** | 链/Agent/图状态机；多 Agent 协作 |
| LLM 推理 | **DeepSeek**(`deepseek-chat`) + DashScope fallback | DeepSeek 中文好且便宜；不放鸡蛋一篮子 |
| 向量数据库 | **Milvus 2.3+** | 单机 docker 跑得起、原生 Partition 隔离 |
| Embedding | **本地 BAAI/bge-small-zh-v1.5**（sentence-transformers 5.5+） | 512 维，~100MB，**0 元运行**，中文质量好 |
| MCP 协议 | **fastmcp 2.x** | 工具拆独立进程，热插拔，CallToolResult dataclass |
| 小红书抓取 | **Playwright 1.59+**（headless Chromium） | 避开 X-S 签名逆向；DOM 解析比内部 API 稳 |
| 前端 | 纯 Vanilla JS + CDN（marked、highlight.js） | 项目要求零构建工具链 |
| 持久化 | **SQLAlchemy 2.0+** + SQLite | 旅游攻略分享链接 |
| 测试 | **pytest 9.0** + pytest-asyncio + pytest-mock | 77 单元测试 + 4 集成测试 |
| 包管理 | **uv** | 比 pip 快 10×，自带虚拟环境 |

### 2.2 XHS RAG 关键架构决策

| 决策 | 选择 | 拒掉的方案 |
|---|---|---|
| 多 KB 隔离 | Milvus 原生 **Partition** | metadata 字段过滤（慢、删除麻烦）、多 collection（资源浪费） |
| Embedding | **本地** sentence-transformers | DashScope（按调用收费）、OpenAI embeddings |
| LLM 是否自动触发 RAG | 用户**手动**选 KB | LLM tool calling 决定（不可控） |
| KB 粒度 | 按 **city**（同 city 多次入库追加） | 每次搜索独立 KB（很快泛滥成 50+） |
| XHS 数据获取 | Playwright **抓 DOM** | 逆向 X-S 签名调内部 API（易碎） |
| 引用展示 | 消息顶部**可折叠** | 消息底部 footnote（要 LLM 配合，不可靠） |
| 命中 0 条时 | 仍走 LLM，prompt 改写"通用建议" | 返 404 错误（用户体验差） |

---

## 三、全链路跑通流程

### 3.1 系统要求

| 组件 | 版本 |
|---|---|
| OS | Windows 11 / macOS / Linux（本文以 Windows + PowerShell 为准） |
| Python | **3.13**（`.python-version` 固定；3.10 不兼容） |
| Docker Desktop | 跑 Milvus |
| 包管理 | `uv`：`pip install uv` |
| LLM Key | DeepSeek（推荐）或 DashScope |

### 3.2 安装步骤

```powershell
# 1. 克隆
git clone <repo>
cd super_biz_agent

# 2. 装依赖
uv venv
.venv\Scripts\activate
uv pip install -e .

# 3. 装 Playwright Chromium（用于 XHS 抓取）
playwright install chromium

# 4. 新建 .env
# 参考第六节复制完整模板，最小必填仅 DEEPSEEK_API_KEY
```

> **首次启动会从 HuggingFace 自动下载 `BAAI/bge-small-zh-v1.5` 模型（~100MB）到 `~/.cache/huggingface/`，仅一次。**

### 3.3 MCP 端口对照表

> ⚠ **Milvus 是所有功能的硬依赖**（主服务启动时会触发 `vector_store_manager` 模块加载并连 Milvus）。即便你只想用旅游 Agent，也要先起 Milvus。

不同功能链路需要起不同的 MCP server。**只起你要用的那条链路对应的 MCP 即可**——多余的 MCP 不起也不影响主服务运行。

| 链路 | 必需 MCP | 端口 | 对应 `.env` 变量 | 备注 |
|---|---|---|---|---|
| ① 普通对话 | 无 | - | - | 只要主服务 + LLM key |
| ② 文件 RAG | 无 | - | - | 主服务 + Milvus |
| ③ **小红书 RAG** | `xhs_server` | 8013 | `MCP_XHS_URL` | 内置 Playwright，~200MB 内存 |
| ④ **旅游 Agent** | `gaode_maps` | 8010 | `MCP_GAODE_URL` | 需 `GAODE_API_KEY` |
|   | `ctrip` | 8011 | `MCP_CTRIP_URL` | Mock 酒店数据 |
|   | `dianping` | 8012 | `MCP_DIANPING_URL` | Mock 餐饮/景点 |

下面给三个**启动配方**，按需挑。

### 3.4 配方 A —— 只跑小红书 RAG（3 窗口）

```powershell
# 窗口 1 — Milvus
docker compose -f vector-database.yml up -d

# 窗口 2 — 小红书 MCP（端口 8013）—— ③ 链路必需
.venv\Scripts\activate
python mcp_servers/xhs_server.py

# 窗口 3 — FastAPI 主服务（端口 9900）
.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
```

**主服务启动成功标志：**

```
SuperBizAgent v1.0.0 启动中...
监听地址: http://0.0.0.0:9900
加载本地 embedding 模型: BAAI/bge-small-zh-v1.5 ...
本地 Embeddings 初始化完成 — 维度: 512
成功连接到 Milvus
collection 'biz' 已加载
```

### 3.5 配方 B —— 跑旅游 Agent（5 窗口）

需要 3 个 MCP（高德 + 携程 + 大众点评）+ Milvus + 主服务。

```powershell
# 窗口 1 — Milvus
docker compose -f vector-database.yml up -d

# 窗口 2 — 高德地图 MCP（端口 8010）—— 必需，需 GAODE_API_KEY
.venv\Scripts\activate
python mcp_servers/gaode_maps.py

# 窗口 3 — 携程 MCP（端口 8011, mock 数据）
.venv\Scripts\activate
python mcp_servers/ctrip.py

# 窗口 4 — 大众点评 MCP（端口 8012, mock 数据）
.venv\Scripts\activate
python mcp_servers/dianping.py

# 窗口 5 — FastAPI 主服务
.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
```

> 高德 `GAODE_API_KEY` 没配时：景点/餐厅/酒店会**降级为成都 Mock 数据**——旅游 Agent 仍能跑通，只是数据是预置的。
>
> 同理可加 `AMAP_JS_KEY` + `AMAP_JS_SECURITY_CODE` 让前端旅游工作台的地图渲染出来。

### 3.6 配方 C —— 全开（6 窗口）

同时跑小红书 RAG + 旅游 Agent。

```powershell
# 窗口 1 — Milvus
docker compose -f vector-database.yml up -d

# 窗口 2 — 小红书 MCP（端口 8013）
.venv\Scripts\activate
python mcp_servers/xhs_server.py

# 窗口 3-5 — 旅游 Agent 三个 MCP
.venv\Scripts\activate
python mcp_servers/gaode_maps.py      # 8010

.venv\Scripts\activate
python mcp_servers/ctrip.py           # 8011

.venv\Scripts\activate
python mcp_servers/dianping.py        # 8012

# 窗口 6 — FastAPI 主服务
.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
```

### 3.7 端到端冒烟测试

新开第 4 个 PowerShell 窗口（curl 是 Windows 自带的，不用激活 venv）：

```powershell
# 1. 通过 MCP 抓取小红书笔记并入库到 partition 'xhs_<md5>'
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'

# 首次约 10-15s（Playwright 冷启 chromium）
# 期望返回：
# {"code":200,"data":{"kb_name":"xhs_xxxxxxxx","ingested":5,"chunks":5,
#                     "keyword":"美食","city":"成都"}}

# 2. 列出所有知识库
curl.exe http://localhost:9900/api/xhs/kb/list
# {"code":200,"data":{"total":1,"kbs":[{"kb_name":"xhs_xxxxxxxx",
#                                       "description":"成都",
#                                       "num_entities":5,...}]}}

# 3. 基于该 KB 做 RAG 对话（流式）
curl.exe -N -X POST http://localhost:9900/api/chat/rag_stream `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"成都必吃美食\",\"session_id\":\"smoke-1\",\"kb_name\":\"xhs_xxxxxxxx\"}'
# 预期 SSE 流：
# data: {"type":"citations","data":[{...}]}     ← 引用先到
# data: {"type":"content","data":"根据小红书"}  ← 内容逐 chunk
# data: {"type":"content","data":"攻略，建议..."}
# ...
# data: {"type":"done"}

# 4. 全局检索（不传 kb_name）—— 跨所有 xhs_* 分区
curl.exe -N -X POST http://localhost:9900/api/chat/rag_stream `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"哪个城市好玩\",\"session_id\":\"smoke-2\"}'

# 5. 删除知识库
curl.exe -X DELETE http://localhost:9900/api/xhs/kb/xhs_xxxxxxxx
```

### 3.5 前端浏览器流程

打开 http://localhost:9900：

1. 子模式下拉切到「**RAG · 小红书**」 → 输入框上方淡橙色 KB 选择条浮起（不挤压聊天区）
2. 默认显示「🌐 全部知识库」表示跨分区检索
3. 点 KB 选择条 → 右侧 420px 抽屉滑出
4. 抽屉顶部表单填入 关键词 + 城市 + 数量 → 点「搜索并入库」→ spinner → 入库成功 → 新 KB 自动选中
5. 抽屉里点某个城市 KB → 抽屉关闭，KB bar 显示「📍 成都」
6. 输入问题 → 发送 → 助手回答顶部出现可折叠的「📕 基于 N 条小红书攻略」+ 流式正文

---

## 四、功能详解

### 4.1 普通对话（① 快速 / 流式）

- 快速模式 `/api/chat`：阻塞返回完整答案
- 流式模式 `/api/chat_stream`：SSE 逐字推送
- 同一 `session_id` 在所有聊天接口间历史**连续**
- LLM 默认 DeepSeek，fallback DashScope

### 4.2 文件 RAG（② 上传文档 + 索引）

- `POST /api/upload`（multipart）— 支持 `.md`/`.txt`/`.pdf`/`.docx`
- 自动切块（`chunk_max_size=800` / `overlap=100`）入 Milvus `_default` 分区
- 与 XHS RAG 的 `xhs_*` 分区**完全隔离**

### 4.3 小红书动态 RAG（③ 本期核心）

**数据流：**

```
入库链路（按需触发）
└── POST /api/xhs/ingest/mcp { keyword, city, count }
        ↓
   xhs_ingestion_service
   ├── kb_name = "xhs_<md5(city)前8位>"  (按 city 分库)
   ├── 调 fastmcp Client → xhs_server (8013)
   │       └── Playwright 启 chromium 打开
   │           search_result?keyword=城市+关键词
   │           解析 DOM 抽笔记列表
   ├── 切块（RecursiveCharacterTextSplitter）
   ├── 本地 embedding (BAAI/bge-small-zh-v1.5, 512 维)
   └── pymilvus collection.insert(partition_name=kb_name)
        ↓
   返回 { kb_name, ingested, chunks, keyword, city }

对话链路
└── POST /api/chat/rag_stream { Question, session_id, kb_name? }
        ↓
   rag_service.build_rag_context
   ├── kb_name 给定 → similarity_search_in_partition()
   └── kb_name 空/null → similarity_search_across_kb_partitions()
                          （只跨 xhs_* 分区，不污染 _default）
        ↓
   citations 按 note_id 去重
   构造 messages = [SystemPrompt + 参考资料,
                     ...history[-20:],
                     HumanMessage]
        ↓
   LLMFactory.create_travel_llm(streaming=True).astream
        ↓
   SSE: citations → content × N → done

管理链路
├── GET    /api/xhs/kb/list           列出所有 xhs_* 分区
└── DELETE /api/xhs/kb/{kb_name}       释放 + drop_partition
```

**KB 命名**：`xhs_<md5(city.strip())前8位>`

- "成都" → `xhs_a3f9c1b2`
- "北京" → `xhs_8d4e2f01`
- 空 city → `xhs_global`

**前端关键交互：**

- **KB 选择条**（输入框上方）：`absolute` 浮动，不占文档流；切换 RAG 模式时聊天区高度**不变**
- **KB 抽屉**（右侧 420px）：搜索入库表单 + KB 列表（含两步确认删除）
- **KB 卡片**：location pin SVG + city 名（15px/600）+ 笔记数/创建时间
- **引用折叠条**：消息顶部 `<details>`，默认折叠，点开看 `[1] 标题 · 作者 · 8832 赞`
- **会话连续性**：同 `session_id` 在 `/chat` 和 `/chat/rag` 间历史共享

### 4.4 旅游多智能体规划（④）

LangGraph 子图嵌套架构。6 Agent 协作：

```
ParserAgent → 解析"成都 3 日游 预算 3000"为结构化 trip
   ↓
   ├─→ AttractionAgent  (高德 POI 查景点)
   ├─→ RouteAgent       (高德 driving 路线)
   ├─→ HotelAgent       (携程 mock)
   └─→ FoodAgent        (大众点评 mock)
   ↓ ← 三路并行
StrategyAgent → 综合 final_plan + structured_plan
```

`POST /api/travel/plan` SSE 流式，输出 6 Agent 中间事件 + 最终 `structured_plan`。

---

## 五、API 接口

完整端点见 http://localhost:9900/docs。核心一览：

### 5.1 普通对话

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/chat` | 阻塞对话 |
| POST | `/api/chat_stream` | SSE 流式 |
| GET | `/api/chat/session/{session_id}` | 拿会话历史 |
| POST | `/api/chat/clear` | 清空会话 |

### 5.2 小红书 RAG

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/xhs/ingest/mcp` | 调 MCP 搜索 + 入 partition |
| POST | `/api/xhs/ingest/text` | 手动粘贴笔记入库 |
| GET | `/api/xhs/kb/list` | 列出所有 `xhs_*` 分区 |
| DELETE | `/api/xhs/kb/{kb_name}` | 删除分区 |
| GET | `/api/xhs/stats` | biz collection 总向量数 |
| POST | `/api/chat/rag` | RAG 阻塞对话 |
| POST | `/api/chat/rag_stream` | RAG 流式（含 citations） |

### 5.3 `/api/chat/rag_stream` 请求体

```jsonc
{
  "Question":   "成都必吃美食推荐",
  "session_id": "u-001",
  "kb_name":    "xhs_a3f9c1b2",   // 可选；空 → 跨所有 xhs_* 分区全局检索
  "top_k":      3                  // 可选，默认 3
}
```

### 5.4 SSE 事件协议

```
data: {"type":"citations","data":[{"title":"成都5日游","url":"...","author":"...","likes":8832}, ...]}

data: {"type":"content","data":"根据小红书"}
data: {"type":"content","data":"攻略，建议..."}
...
data: {"type":"done"}
```

异常：

```
data: {"type":"error","data":"知识库 'xhs_xxx' 不存在"}
```

### 5.5 旅游多智能体

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/travel/plan` | SSE 流式规划，6 Agent 中间事件 + final |
| GET | `/api/travel/map-key` | 前端用的高德 JS API key |
| POST | `/api/travel/share` | 生成攻略分享链接 |
| GET | `/api/travel/share/{id}` | 查看分享攻略 |

### 5.6 健康检查

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/health` | 主服务 + Milvus 连接状态 |

---

## 六、.env 配置

新建 `.env` 在项目根目录，**最小必填仅 LLM key**。

```ini
# ── 应用 ─────────────────────────────────────────────
APP_NAME=SuperBizAgent
DEBUG=True
HOST=0.0.0.0
PORT=9900

# ── LLM ─────────────────────────────────────────────
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# DashScope 作 fallback（可选）
DASHSCOPE_API_KEY=
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-max

# ── Milvus 向量库 ───────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_TIMEOUT=10000

# ── RAG ─────────────────────────────────────────────
RAG_TOP_K=3
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100

# ── 小红书 MCP / RAG（功能 ③）──────────────────────
MCP_XHS_URL=http://localhost:8013/mcp
# Playwright 浏览器 cookie（浏览器 F12 复制 xiaohongshu.com 的 Cookie 整行）
# 不填 → headless chromium 未登录访问，可能拿不到结果
XHS_COOKIE=

# ── 旅游 Agent MCP（功能 ④）─────────────────────────
MCP_GAODE_URL=http://localhost:8010/mcp
MCP_CTRIP_URL=http://localhost:8011/mcp
MCP_DIANPING_URL=http://localhost:8012/mcp
GAODE_API_KEY=                # https://lbs.amap.com（Web 服务）
AMAP_JS_KEY=                  # 前端地图（Web JS API）
AMAP_JS_SECURITY_CODE=

# ── 分享链接 ────────────────────────────────────────
SHARE_DB_URL=sqlite:///data/shares.db
```

---

## 七、测试用例

### 7.1 跑测试

```powershell
.venv\Scripts\activate

# 全量单元测试（不需要 Milvus / MCP，全 mock）
python -m pytest tests/ -v --no-cov
# → 77 passed, 4 skipped

# Milvus 集成测试（需 Milvus 跑着）
$env:RUN_MILVUS_TESTS="1"
python -m pytest tests/services/test_vector_store_partition_integration.py -v --no-cov
# → 4 passed
```

### 7.2 测试覆盖矩阵（共 81 个测试）

| 测试文件 | 数量 | 覆盖点 |
|---|---|---|
| `tests/services/test_session_store.py` | 5 | 跨 endpoint 共享会话：get/append/clear 隔离 |
| `tests/services/test_vector_store_manager_partition.py` | 9 | Milvus partition CRUD（mock collection） |
| `tests/services/test_xhs_ingestion_service.py` | 7 | `_make_kb_name` 确定性、0 笔记不创建分区 |
| `tests/services/test_rag_service.py` | 4 | citations 去重、空命中 fallback、history 截 20、KB 不存在 |
| `tests/api/test_xhs_api.py` | 6 | ingest_mcp 返 kb_name、list、delete 404 |
| `tests/api/test_chat_rag_api.py` | 5 | RAG happy path、KB 不存在、SSE 事件顺序 |
| `tests/api/test_travel.py` | 7 | 旅游 SSE 端到端、structured_plan 字段 |
| `tests/db/test_share_store.py` | 3 | SQLite 攻略分享 |
| `tests/agent/travel/*` | 31 | 6 Agent 测试 + state + geo_utils + parser |
| `tests/services/test_vector_store_partition_integration.py` | 4 | Milvus 真集成（默认 skip） |
| **总计** | **81** | **77 单元 + 4 集成** |

### 7.3 关键测试场景

**SSE 事件顺序**（`test_chat_rag_stream_emits_citations_then_content_then_done`）：

- 第一个事件**必须**是 `citations`
- 然后是若干 `content`
- 最后 `done`

**citations 去重**（`test_build_rag_context_hits_nonempty`）：

- 3 个 docs，其中 2 个 `note_id="n1"`
- 期望 citations 只保留 2 条（按 note_id 去重）

**Milvus 跨 partition 隔离**（集成测试 `test_partition_isolation`）：

- 创建 KB_A 写"cheese pizza"
- 创建 KB_B 写"green tea"
- 查 KB_A "pizza" → 必须命中
- 查 KB_B "pizza" → 必须**不**命中

---

## 八、项目演进过程

完整 commit 历史按时间分阶段：

### Phase 1 ── 2026-05-12: 项目基线

- 基础设施：DashScope 通义 + Milvus + LangChain + FastAPI + MCP 协议

### Phase 2 ── 2026-05-13: 转向旅游 Agent

`5cc62a4 → b1c062e`（约 50 commit）

- **6 个旅游 Agent** 全部上线：Parser / Attraction / Route / Hotel / Food / Strategy
- **LangGraph 三阶段**：Parser → (Attraction / Route / Hotel / Food 并行) → Strategy
- **MCP server**：高德地图（POI / 路线）/ 携程 mock / 大众点评 / 美团 scaffold
- 主流程编排（`travel_service.plan`）+ SSE 流式 API
- 前端**旅游工作台**：两栏布局（左表单 + 右地图）、攻略卡片、分享链接（SQLite + SQLAlchemy）
- 高德 JS API 集成：景点 marker、路线 polyline、按 day 高亮
- 多版本 UX 迭代：
  - **v1.2.4** 食物表格 + 自定义 SVG marker
  - **v1.2.5** 智能路线规划（步行/骑行/地铁/打车）+ 天气小组件
  - **v1.2.6** 坐标稳定性修复（后端 Gaode REST + 前端 fallback）
- LLM 切到 **DeepSeek V4 Pro**（移除 ChatQwen 依赖）

### Phase 3 ── 2026-05-14: 小红书 RAG 后端

`03846d8 → eb9bde8`（17 commit）

- 写 spec `docs/superpowers/specs/2026-05-14-xhs-rag-dynamic-kb-design.md`
- 写 plan `docs/superpowers/plans/2026-05-14-xhs-rag-dynamic-kb.md`（11 个 TDD task）
- **Inline Execution** 模式执行：
  - Task 1：`session_store` 抽离（chat.py 重构）
  - Task 2-3：`VectorStoreManager` 加 5 个 partition 方法（ensure/list/drop/insert/search）
  - Task 4：`xhs_ingestion_service` 自动生成 kb_name、走 partition
  - Task 5：`/api/xhs/*` 加 list/delete + kb_name 校验
  - Task 6：`rag_service.build_rag_context` 含 citations 去重、空命中 fallback
  - Task 7-8：`/api/chat/rag` 阻塞 + `/api/chat/rag_stream` SSE 流式
  - Task 9：`main.py` 注册路由
  - Task 10：Milvus 集成测试（4 个）
- **77 单元测试全过**

### Phase 4 ── 2026-05-14~15: 小红书 RAG 前端

`034ebdc → 3d4475b`（11 commit）

- 前端 spec + plan
- **Subagent-Driven Development** 模式执行 9 个 task，每 task 三阶段 review：
  1. HTML 骨架（dropdown / KB bar / drawer）
  2. CSS 一次性加完（220+ 行）
  3. JS 状态 + DOM 缓存 + RAG 子模式钩入
  4. `fetchKbList` / `renderKbList` / `selectKb`
  5. 抽屉开关 + 事件绑定
  6. 删除 + 两步确认
  7. 搜索入库（MCP）
  8. `sendMessage` RAG 分支 + `sendRagStream` SSE + citations 渲染
- 22 项端到端浏览器手测清单

### Phase 5 ── 2026-05-15: 兼容性与替换（实战修复）

| Commit | 问题 → 解决 |
|---|---|
| `f734e4d` | **fastmcp 升级 API 变了**：`client.call_tool()` 返回 `CallToolResult` dataclass（不再 list[TextContent]）→ 改用 `.data` 属性 |
| `1a7fb8d` | **DashScope embedding 账户欠费** → 切到本地 `BAAI/bge-small-zh-v1.5`（sentence-transformers），维度 1024→512，Milvus collection 自动重建 |
| `6660e52` | **XHS 内部 API 需 X-S 签名逆向**（脆弱）→ 改用 **Playwright headless chromium** 解析 search_result 页面 DOM，避开签名 |

### Phase 6 ── 2026-05-15: v2 体验优化

| Commit | 改动 |
|---|---|
| `cdcf834` | **按 city 分库**：同 city 多次入库追加到同一 partition；不选 KB → 跨所有 `xhs_*` 分区全局检索；前端 KB bar 紧凑居中、加「🌐 全部知识库」默认项 |
| `77010c5` | KB 卡片**强调 city 名**（15px/600 + location pin SVG 圆形 tile）；emoji 🗑 → trash SVG；删除按钮 focus-visible 红色 outline |
| `5cb532a` | 修两个 bug：① 全局检索 422（前端 `kb_name: null` → 后端 pydantic 拒绝；改 `Optional[str]` + 前端 fallback）② KB 显示「(未命名)」（Milvus partition.description 不持久化 → list 接口回退 query 一条样本的 `metadata.city`） |
| `23804d2` | KB bar 改 **`position: absolute`** 浮动定位，不再挤压聊天区高度 |

### Phase 7 ── 2026-05-15: 文档

- `FULL_README.md` — 5 条链路通用启动指南
- `README_Final.md` — 单文件完整对外文档
- 本文件 `README.md` — **加入"项目演进过程"章节**

---

## 九、系统架构

### 9.1 目录结构

```
super_biz_agent/
├── app/
│   ├── main.py                          # FastAPI 入口
│   ├── config.py                        # pydantic-settings 配置
│   ├── api/
│   │   ├── chat.py                      # ① 普通对话
│   │   ├── chat_rag.py                  # ③ XHS RAG 对话
│   │   ├── xhs.py                       # ③ XHS KB 管理
│   │   ├── travel.py                    # ④ 旅游 Agent
│   │   ├── file.py                      # ② 文件上传
│   │   └── health.py
│   ├── agent/
│   │   ├── travel/                      # 6 个旅游 Agent
│   │   └── mcp_client.py
│   ├── services/
│   │   ├── rag_service.py               # build_rag_context
│   │   ├── session_store.py             # 共享会话
│   │   ├── vector_store_manager.py      # Milvus + partition 方法
│   │   ├── vector_embedding_service.py  # 本地 bge embedding
│   │   ├── xhs_ingestion_service.py     # XHS 入库管道
│   │   └── travel_service.py            # 旅游 Agent 编排
│   ├── core/
│   │   ├── llm_factory.py               # DeepSeek/DashScope 工厂
│   │   └── milvus_client.py             # biz collection (512 维)
│   └── ...
├── mcp_servers/
│   ├── xhs_server.py                    # 端口 8013 Playwright
│   ├── gaode_maps.py                    # 端口 8010
│   ├── ctrip.py                         # 端口 8011 mock
│   └── dianping.py                      # 端口 8012 mock
├── static/
│   ├── index.html                       # 单页前端
│   ├── app.js                           # 主应用 + TravelUI + XHS RAG
│   └── styles.css                       # 所有样式
├── tests/                               # 81 个测试
├── docs/
│   └── superpowers/
│       ├── specs/                       # 设计文档
│       └── plans/                       # 实施计划
├── vector-database.yml                  # Milvus docker-compose
├── pyproject.toml                       # 依赖（uv）
├── .env                                 # 配置（自建）
├── README.md                            # 👉 本文档
├── README_Final.md                      # 早期完整版（同内容备份）
└── FULL_README.md                       # 5 链路通用启动手册
```

### 9.2 XHS RAG 模块依赖

```
                      前端 (static/app.js)
                          │
                          ▼ HTTP / SSE
              ┌──────────────────────────────┐
              │  FastAPI 主服务 (uvicorn)    │
              └──────────────────────────────┘
                          │
        ┌─────────────────┼──────────────────────┐
        ▼                 ▼                      ▼
   app/api/xhs.py    app/api/chat_rag.py    app/api/chat.py
        │                 │                      │
        ▼                 ▼                      ▼
 xhs_ingestion   rag_service.py            session_store
        │              │
        │              ▼
        │       vector_store_manager.py ─→ pymilvus ─→ Milvus
        │              │
        │              └→ vector_embedding_service.py
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

## 十、故障排查

### 10.1 启动期

| 症状 | 原因 / 处理 |
|---|---|
| `Fail connecting to server on localhost:19530` | Milvus 没起：`docker ps`；`docker compose -f vector-database.yml up -d` |
| `RuntimeError: 向量维度不匹配` | 旧 collection 维度不是 512 → 自动 drop 重建，等几秒 |
| 启动慢（30s+ 才打印 Embeddings 初始化完成） | 首次 sentence-transformers 在下模型（~100MB） |
| `playwright._impl._errors.Error: Executable doesn't exist` | chromium 没装：`playwright install chromium` |

### 10.2 入库期（`/api/xhs/ingest/mcp`）

| 症状 | 原因 / 处理 |
|---|---|
| `{"code":500,"message":"MCP 连接失败: ..."}` | 窗口 2 的 `xhs_server.py` 没起 |
| `{"code":200,"data":{"kb_name":null,"ingested":0}}` | Playwright 抓到了页面但没解析出笔记 → 看 `mcp_servers/xhs_debug.png` 与 `xhs_debug.html` |
| 入库非常慢（> 30s） | Playwright 冷启 chromium ~3s + XHS 加载 + 解析 |
| Cookie 失效 | 重新从浏览器 F12 拿 cookie，更新 `.env` 的 `XHS_COOKIE`，**重启窗口 2** |

### 10.3 对话期

| 症状 | 原因 / 处理 |
|---|---|
| "以下为通用建议..." | 该 query 没命中 KB 任何 chunk → 设计行为，不是错 |
| 红字"知识库 'xxx' 不存在" | 该 KB 被删了；先 `GET /api/xhs/kb/list` |
| 红字"网络错误" | 主服务挂了 |
| KB 显示"(未命名)" | Milvus partition.description 不持久化 → v2 已加 metadata.city 回退；如果还显示需要检查 list 接口日志 |
| 选「全部知识库」提问无响应 | v2 已修：前端 fallback `|| ''` + 后端 `Optional[str]` |

### 10.4 前端

| 症状 | 排查 |
|---|---|
| 切到 RAG 子模式后 KB bar 不出现 | F12 → Console 看 JS 错；Ctrl-F5 强刷拿新 JS |
| KB bar 出现/隐藏时聊天区"跳"一下 | v2 已修：KB bar 改 `position: absolute` 不占文档流 |
| 抽屉打开是空的 | F12 → Network 看 `/api/xhs/kb/list` 返回什么 |

### 10.5 Windows 进程清理

PowerShell 关窗口有时不会 SIGINT 子进程，残留 Python 进程会占用 numpy / chromium DLL：

```powershell
Get-Process python -ErrorAction SilentlyContinue | Format-Table Id,StartTime -AutoSize
Stop-Process -Id <PID> -Force
```

---

## 十一、已知限制与后续方向

### 11.1 已知限制

| 类别 | 描述 |
|---|---|
| XHS 笔记内容 | 列表页只拿到 title 当 content；详情页正文未抓（每条 +5-10s 未做） |
| XHS 反爬 | Cookie 仍可能被风控；Playwright 不能过验证码 |
| Chromium 资源 | xhs_server 进程内常驻 chromium（~200MB 内存） |
| Embedding 多语言 | bge-small-zh 中文专用；英文/日文 query 质量下降 |
| Milvus 单机 | docker-compose 是 standalone；KB > 100 个时考虑分布式 |
| 前端测试 | 没有 Jest/Vitest，靠手工 22 项 smoke test |
| localStorage 跨 tab | 多 tab 删除 KB 不会主动通知其他 tab |

### 11.2 后续可做

1. **进详情页抓正文**：让笔记内容长一些，RAG 引用质量大幅提升
2. **多语言 embedding**：换 `BAAI/bge-m3`（多语言，~1.2GB）
3. **跨 tab 实时同步**：用 `storage` 事件或 SSE 推送 KB 列表变更
4. **citations 侧栏预览**：点 citation 在右侧侧栏显示原文 + 图
5. **A/B 评估面板**：对比"开/关 RAG"两种回答
6. **Milvus 索引优化**：当前 IVF_FLAT/L2，可换 HNSW 提速

---

## 许可证

MIT License

Author: chief
