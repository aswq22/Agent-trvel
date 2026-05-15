# SuperBizAgent — 完整启动指南（Windows / PowerShell）

> 本文档覆盖整个项目从零到能跑的**完整**步骤，包含 5 条相对独立的功能链路。按你要用哪条链路启对应的服务即可，不必全部都开。

## 0. 五条功能链路一览

| 功能 | 入口 API | 必须的进程 | 必须的 API Key |
|---|---|---|---|
| ① 普通聊天 | `POST /api/chat`、`/chat_stream` | 主服务 | DeepSeek 或 DashScope（二选一） |
| ② 文件 RAG 问答 | `POST /api/upload` → `/api/chat` | 主服务 + Milvus | DashScope（embedding） |
| ③ **小红书动态 RAG** | `POST /api/chat/rag`、`/chat/rag_stream` | 主服务 + Milvus + xhs MCP | DashScope（embedding） + DeepSeek（LLM） |
| ④ 旅游多智能体 | `POST /api/travel/...` | 主服务 + gaode + ctrip + dianping MCP | DeepSeek + 高德 GAODE_API_KEY |
| ⑤ AIOps 诊断 | `POST /api/aiops` | 主服务 + cls + monitor MCP | DashScope |

后面每一节会注明"如果你想用功能 X，需要做哪几步"。

---

## 1. 系统要求

- **Windows 11** + **PowerShell**（CMD 也行，本文以 PowerShell 为准）
- **Python 3.13**（项目用 `.python-version` 固定到 3.13；3.10 不兼容）
- **Docker Desktop**（开 Milvus 用）
- **uv**（可选但推荐，比 pip 快 10 倍）：`pip install uv`
- 至少一个 LLM Key：
  - **DeepSeek Key**（推荐，便宜）：https://platform.deepseek.com/
  - **DashScope Key**（阿里通义）：https://bailian.console.aliyun.com/?tab=api-key
- 想用旅游 Agent → 还要 **高德 Web 服务 Key**：https://lbs.amap.com 注册免费拿
- 想用真实小红书抓取 → 浏览器 cookie（可选，不配走 mock）

---

## 2. 第一次启动（一次性步骤）

### 2.1 克隆并安装依赖

```powershell
git clone <repository_url>
cd super_biz_agent

# 用 uv（推荐）
uv venv
.venv\Scripts\activate
uv pip install -e .

# 或者用 pip
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

### 2.2 配置 `.env`

项目根目录新建 `.env`，按需填入。**至少要有 `DASHSCOPE_API_KEY`**（用于 embedding，所有 RAG 都靠它），`DEEPSEEK_API_KEY` 任何 LLM 调用都强烈推荐配上。

```ini
# ── 应用 ────────────────────────────────────────────
APP_NAME=SuperBizAgent
DEBUG=True
HOST=0.0.0.0
PORT=9900

# ── LLM ─────────────────────────────────────────────
# 旅游 Agent / 普通 Chat / RAG 对话 优先用 DeepSeek
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_API_BASE=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat

# Embedding 必须用 DashScope（1024 维 text-embedding-v4）
# AIOps 用 qwen-max
DASHSCOPE_API_KEY=sk-...
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
DASHSCOPE_MODEL=qwen-max
DASHSCOPE_EMBEDDING_MODEL=text-embedding-v4

# ── Milvus ──────────────────────────────────────────
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_TIMEOUT=10000

# ── RAG ─────────────────────────────────────────────
RAG_TOP_K=3
RAG_MODEL=qwen-max
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100

# ── AIOps MCP（功能 ⑤）─────────────────────────────
MCP_CLS_TRANSPORT=streamable-http
MCP_CLS_URL=http://localhost:8003/mcp
MCP_MONITOR_TRANSPORT=streamable-http
MCP_MONITOR_URL=http://localhost:8004/mcp

# ── 旅游 Agent MCP（功能 ④）─────────────────────────
MCP_GAODE_URL=http://localhost:8010/mcp
MCP_CTRIP_URL=http://localhost:8011/mcp
MCP_DIANPING_URL=http://localhost:8012/mcp
GAODE_API_KEY=                # https://lbs.amap.com
AMAP_JS_KEY=                  # 前端地图展示（可选）
AMAP_JS_SECURITY_CODE=        # JS API 2.0 必填

# ── 小红书 RAG MCP（功能 ③）─────────────────────────
MCP_XHS_URL=http://localhost:8013/mcp
# 不填 → 走 Mock 数据；填了 → 走真实 search（cookie 易失效）
XHS_COOKIE=

# ── 分享链接（旅游 Agent 分享功能用）────────────────
SHARE_DB_URL=sqlite:///data/shares.db
```

---

## 3. 启动 Milvus（功能 ②③ 必需）

```powershell
docker compose -f vector-database.yml up -d
# 等约 10 秒首启
docker ps --filter "name=milvus" --format "{{.Names}}: {{.Status}}"
# 看到 milvus-standalone: Up ... 即就绪
```

> 端口 19530（gRPC）+ 9091（管理 UI，不强制）。

---

## 4. 启动 MCP Server（按你要用哪条链路开）

每个 MCP 都是**独立进程**，需要单独 PowerShell 窗口（或后台运行）。每个窗口都要先：

```powershell
.venv\Scripts\activate
```

下面**只列你用得到的**。

### 4.1 小红书 RAG —— 功能 ③

```powershell
python mcp_servers/xhs_server.py          # 端口 8013
# 看到 "Uvicorn running on http://0.0.0.0:8013" 即就绪
```

### 4.2 旅游多智能体 —— 功能 ④

需要 3 个 MCP：

```powershell
# 窗口 A
python mcp_servers/gaode_maps.py          # 端口 8010
# 窗口 B
python mcp_servers/ctrip.py               # 端口 8011（mock 数据）
# 窗口 C
python mcp_servers/dianping.py            # 端口 8012（mock 数据）
```

### 4.3 AIOps —— 功能 ⑤

```powershell
# 窗口 A
python mcp_servers/cls_server.py          # 端口 8003
# 窗口 B
python mcp_servers/monitor_server.py      # 端口 8004
```

### 4.4 ⚠ 端口冲突提示

`mcp_servers/meituan.py` 也监听 **8013**，与 `xhs_server.py` 冲突。当前 `config.py` 没接入 meituan（旅游 Agent 用 dianping 8012 替代），但如果你哪天想跑 meituan：

- 改 `meituan.py` 末尾的 `port=8013` 成别的端口（如 8014）
- 别和 `xhs_server.py` 同时启

### 4.5 全部 MCP 端口表

| MCP | 端口 | 配置变量 | 功能链路 |
|---|---|---|---|
| `xhs_server` | 8013 | `MCP_XHS_URL` | ③ XHS RAG |
| `gaode_maps` | 8010 | `MCP_GAODE_URL` | ④ 旅游 |
| `ctrip` | 8011 | `MCP_CTRIP_URL` | ④ 旅游 |
| `dianping` | 8012 | `MCP_DIANPING_URL` | ④ 旅游 |
| `cls_server` | 8003 | `MCP_CLS_URL` | ⑤ AIOps |
| `monitor_server` | 8004 | `MCP_MONITOR_URL` | ⑤ AIOps |
| `meituan` | 8013（冲突） | 未挂载 | — |

---

## 5. 启动主服务（永远必需）

```powershell
.venv\Scripts\activate
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
```

成功标志（控制台输出）：

```
SuperBizAgent v1.0.0 启动中...
监听地址: http://0.0.0.0:9900
API 文档: http://0.0.0.0:9900/docs
成功连接到 Milvus
collection 'biz' 已加载
Share DB 初始化完成
```

访问：

- Web 界面：http://localhost:9900
- Swagger 文档：http://localhost:9900/docs

---

## 6. 各功能验证（curl 冒烟）

### 6.1 ① 普通聊天

```powershell
curl.exe -X POST http://localhost:9900/api/chat `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"你好，介绍一下你自己\",\"session_id\":\"smoke-1\"}'
```

```powershell
# 流式
curl.exe -N -X POST http://localhost:9900/api/chat_stream `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"讲个三句话的笑话\",\"session_id\":\"smoke-1\"}'
```

### 6.2 ② 文件 RAG 问答

```powershell
# 上传文档（任意 .md/.pdf/.docx/.txt 都可，自动切块入库默认分区）
curl.exe -X POST http://localhost:9900/api/upload `
  -F "file=@README.md"

# 然后用 /api/chat 提问；系统会自动检索（注意：这是默认分区 RAG，不是 XHS RAG）
```

### 6.3 ③ 小红书动态 RAG

```powershell
# 1. 用 MCP 搜"美食"，自动建分区入库（Mock 模式默认带 5 条数据）
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'
# 记下 response.data.kb_name

# 2. 看看现有的知识库
curl.exe http://localhost:9900/api/xhs/kb/list

# 3. 基于该 kb 做 RAG 对话
curl.exe -X POST http://localhost:9900/api/chat/rag `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"成都必吃美食有哪些?\",\"session_id\":\"smoke-2\",\"kb_name\":\"<上一步的 kb_name>\"}'

# 4. SSE 流式
curl.exe -N -X POST http://localhost:9900/api/chat/rag_stream `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"3 天行程怎么排\",\"session_id\":\"smoke-2\",\"kb_name\":\"<上一步的 kb_name>\"}'

# 5. 删掉知识库
curl.exe -X DELETE http://localhost:9900/api/xhs/kb/<填 kb_name>
```

### 6.4 ④ 旅游多智能体

```powershell
curl.exe -N -X POST http://localhost:9900/api/travel/plan `
  -H "Content-Type: application/json" `
  -d '{\"user_input\":\"帮我规划成都 3 日游，预算 3000\"}'
# 流式返回 6 个 Agent 的中间事件 + 最终 structured_plan
```

> 旅游 Agent 用 LangGraph 子图嵌套：Parser → (Attraction/Route/Hotel/Food 并行) → Strategy。

### 6.5 ⑤ AIOps 故障诊断

```powershell
curl.exe -N -X POST http://localhost:9900/api/aiops `
  -H "Content-Type: application/json" `
  -d '{\"session_id\":\"smoke-3\"}'
# 流式输出 Plan-Execute-Replan 的全过程
```

### 6.6 健康检查

```powershell
curl.exe http://localhost:9900/health
```

---

## 7. 后续重启 / 停止 / 清理

### 7.1 重启某个 MCP

直接在对应窗口 Ctrl-C 再 `python mcp_servers/<...>.py`。

### 7.2 停掉所有进程

PowerShell 没有现成 `stop-all`，简单方式：

```powershell
# 找出占用 9900 / 8013 / 8010 / 8011 / 8012 / 8003 / 8004 的 PID
netstat -ano | findstr ":9900 :8013 :8010 :8011 :8012 :8003 :8004"

# 杀掉（替换实际 PID）
taskkill /F /PID <PID>
```

或者用项目自带脚本（旧的，覆盖 AIOps 那套）：

```powershell
.\stop-windows.bat
```

### 7.3 停 Milvus

```powershell
docker compose -f vector-database.yml stop
# 想顺便清数据：docker compose -f vector-database.yml down -v
```

### 7.4 一键脚本

项目自带的 `start-windows.bat` 只启 **Milvus + cls + monitor + 主服务**（功能 ①②⑤），不包括旅游和 XHS RAG 的 MCP。要用 ③④ 时需要手动开对应窗口。

---

## 8. 自动化测试

```powershell
.venv\Scripts\activate

# 全量单元测试（不需要 Milvus 也不需要 MCP）
python -m pytest tests/ -v --no-cov

# Milvus 集成测试（需要 Milvus 在 19530 跑着）
$env:RUN_MILVUS_TESTS="1"
python -m pytest tests/services/test_vector_store_partition_integration.py -v --no-cov
```

预期：

- 单元 77 passed
- 集成默认 skipped；设置 `RUN_MILVUS_TESTS=1` 后 4 passed

---

## 9. 项目结构（关键目录）

```
super_biz_agent/
├── app/
│   ├── main.py                            # FastAPI 入口
│   ├── config.py                          # .env 配置加载
│   ├── api/
│   │   ├── chat.py                        # 功能 ① ②
│   │   ├── chat_rag.py                    # 功能 ③
│   │   ├── xhs.py                         # 功能 ③ 管理接口
│   │   ├── travel.py                      # 功能 ④
│   │   ├── file.py                        # 文件上传
│   │   └── health.py
│   ├── agent/
│   │   ├── travel/                        # 6 个旅游 Agent
│   │   └── aiops/                         # 功能 ⑤ Plan-Execute-Replan
│   ├── services/
│   │   ├── rag_service.py                 # 功能 ③ 检索 + prompt + citations
│   │   ├── session_store.py               # 跨 endpoint 共享会话
│   │   ├── vector_store_manager.py        # Milvus + 5 个 partition 方法
│   │   ├── xhs_ingestion_service.py       # XHS 入库管道
│   │   └── ...
│   └── core/
│       ├── llm_factory.py                 # DeepSeek/DashScope 工厂
│       └── milvus_client.py               # biz collection 单例
├── mcp_servers/
│   ├── xhs_server.py                      # 功能 ③（8013）
│   ├── gaode_maps.py                      # 功能 ④（8010）
│   ├── ctrip.py / dianping.py             # 功能 ④（8011/8012, mock）
│   ├── cls_server.py / monitor_server.py  # 功能 ⑤（8003/8004）
│   └── meituan.py                         # 闲置（端口与 xhs 冲突）
├── tests/                                 # 77 单元 + 4 集成测试
├── vector-database.yml                    # Milvus docker-compose
├── .env                                   # 你要新建并填的
├── README.md                              # 旧版（原 AIOps 项目）+ 新追加 XHS 章节
└── FULL_README.md                         # 本文件
```

---

## 10. 常见问题

| 症状 | 原因 / 处理 |
|---|---|
| 主服务启动报 `Fail connecting to server on localhost:19530` | Milvus 没起或没 ready；`docker ps` 检查 |
| `RuntimeError: 向量维度不匹配` | 旧 collection 维度不是 1024，主服务**会自动 drop 重建**，等几秒重试 |
| `/api/chat/rag` 返 400 "kb_name 必填" | 请求体里漏了 `kb_name` |
| `/api/chat/rag` 返 404 | `kb_name` 不存在；先 `GET /api/xhs/kb/list` 看真实分区名 |
| LLM 输出"以下为通用建议" | 该 kb 没检索到相关内容，是设计预期（不报错） |
| 旅游 Agent 卡在 attraction 阶段 | 高德 MCP（8010）没起或 `GAODE_API_KEY` 没配 → 会降级到成都 Mock |
| AIOps 没数据 | cls/monitor MCP 没起；这两个本身也是 mock 实现 |
| 端口被占 | `netstat -ano \| findstr :端口` 找 PID，`taskkill /F /PID <PID>` |
| `make` 不可用 | Windows 用 `.\start-windows.bat` 或本文档手动方式 |
| PowerShell 脚本被禁 | `Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process`（管理员） |

---

## 11. 最小启动配方（按需求挑一个）

**只想跑普通聊天**（功能 ①）

```
1. .env 填 DEEPSEEK_API_KEY
2. uvicorn app.main:app --port 9900
```

**想跑小红书 RAG**（功能 ③）

```
1. .env 填 DEEPSEEK_API_KEY + DASHSCOPE_API_KEY
2. docker compose -f vector-database.yml up -d
3. (窗口 A) python mcp_servers/xhs_server.py
4. (窗口 B) uvicorn app.main:app --port 9900
5. curl /api/xhs/ingest/mcp → 拿 kb_name → curl /api/chat/rag
```

**想跑旅游 Agent**（功能 ④）

```
1. .env 填 DEEPSEEK_API_KEY + DASHSCOPE_API_KEY + GAODE_API_KEY
2. docker compose -f vector-database.yml up -d
3. (窗口 A) python mcp_servers/gaode_maps.py
4. (窗口 B) python mcp_servers/ctrip.py
5. (窗口 C) python mcp_servers/dianping.py
6. (窗口 D) uvicorn app.main:app --port 9900
```

**全开**（①②③④⑤）

```
按 §3 §4.1 §4.2 §4.3 §5 顺序开 9 个进程：
1 Milvus + 6 MCP + 1 主服务 + (前端浏览器)
```
