# SuperBizAgent

> 企业级智能对话和运维助手，支持 RAG 知识库问答和 AIOps 智能诊断

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![LangChain](https://img.shields.io/badge/LangChain-latest-orange.svg)](https://www.langchain.com/)

## ✨ 核心特性

- 🤖 **智能对话** - LangChain 多轮对话 + 流式输出
- 📚 **RAG 问答** - 向量检索增强，支持文档上传、自动建立向量索引、自动更新知识库
- 📕 **小红书 RAG** - 通过 MCP 抓取小红书旅游攻略动态建立 Milvus 分区，聊天时手动切换知识库（详见末尾章节）
- 🔧 **AIOps 诊断** - Plan-Execute-Replan 自动故障诊断和根因分析
- 🌐 **Web 界面** - 现代化 UI，支持多种对话模式：快速问答/流式对话
- 🔌 **MCP 集成** - 日志查询和监控数据工具接入

## 🛠️ 技术栈

- **框架**: FastAPI + LangChain + LangGraph
- **LLM**: 阿里云 DashScope (通义千问)
- **向量库**: Milvus
- **工具协议**: MCP (Model Context Protocol)

## 🚀 快速开始

### 环境要求
- Python 3.10+
- 阿里云 DashScope API Key ([获取地址](https://dashscope.aliyun.com/))

### 安装和启动

#### Linux/macOS 环境

```bash
# 1. 克隆项目
git clone <repository_url>
cd super_biz_agent_py

# 2. 安装依赖（推荐使用 uv）
# 方式 1: 使用 uv（推荐，更快）
pip install uv
uv venv
source .venv/bin/activate
uv pip install -e .

# 方式 2: 使用 pip
pip install -e .

# 3. 编辑配置文件
# 首次使用需要编辑 .env 文件，填入你的 DASHSCOPE_API_KEY
vim .env  # 或使用其他编辑器

# 4. 一键初始化（启动 Docker + 服务 + 上传文档）
make init

# 5. 一键启动
make start
```

#### Windows 环境（PowerShell/CMD）

如果Windows 不支持 `make` 命令，可以手动执行以下步骤以启动服务：

```powershell
# 1. 克隆项目
git clone <repository_url>
cd super_biz_agent_py

# 2. 创建虚拟环境并安装依赖
# 方式 1: 使用 uv（推荐，更快）
pip install uv
# 创建虚拟环境
uv venv
# 激活虚拟环境
.venv\Scripts\activate
# 安装所有依赖
uv pip install -e .

# 方式 2: 使用 pip
python -m venv .venv
.venv\Scripts\activate
pip install -e .

# 3. 编辑配置文件
# 使用记事本或其他编辑器打开 .env 文件，填入你的 DASHSCOPE_API_KEY
notepad .env

# 4. 启动 Docker Desktop
# 确保 Docker Desktop 已安装并正在运行

# 5. 启动 Milvus 向量数据库（Docker Compose）
docker compose -f vector-database.yml up -d

# 6. 等待 Milvus 启动完成（约 5-10 秒）
timeout /t 10

# 7. 启动 MCP 服务
# 启动 CLS 日志查询服务（新开一个 PowerShell 窗口）
python mcp_servers/cls_server.py

# 启动 Monitor 监控服务（新开一个 PowerShell 窗口）
python mcp_servers/monitor_server.py

# 8. 启动 FastAPI 主服务（新开一个 PowerShell 窗口）
# 注意：日志会自动输出到 logs\app_YYYY-MM-DD.log
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900

# 9. 上传文档到向量库（新开一个 PowerShell 窗口）
# 等待服务启动完成后执行
timeout /t 5
python -c "import requests, os, time; [requests.post('http://localhost:9900/api/upload', files={'file': open(f'aiops-docs/{f}', 'rb')}) or time.sleep(1) for f in os.listdir('aiops-docs') if f.endswith('.md')]"
```

**Windows 一键启动脚本**（推荐）

使用启动脚本：

```powershell
# 启动所有服务
.\start-windows.bat

# 停止所有服务
.\stop-windows.bat
```

### 访问服务
- **Web 界面**: http://localhost:9900
- **API 文档**: http://localhost:9900/docs

## 📡 API 接口

### 核心接口

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 普通对话 | POST | `/api/chat` | 一次性返回 |
| 流式对话 | POST | `/api/chat_stream` | SSE 流式输出 |
| AIOps 诊断 | POST | `/api/aiops` | 自动故障诊断（流式） |
| 文件上传 | POST | `/api/upload` | 上传并索引文档 |
| 健康检查 | GET | `/api/health` | 服务状态检查 |
| RAG 对话 | POST | `/api/chat/rag` | 基于 XHS 知识库检索后回答（阻塞） |
| RAG 流式对话 | POST | `/api/chat/rag_stream` | 同上，SSE 流式 |
| MCP 入库 | POST | `/api/xhs/ingest/mcp` | 调小红书 MCP 搜索 → 自动建分区入库 |
| 文本入库 | POST | `/api/xhs/ingest/text` | 手动粘贴笔记入库 |
| 知识库列表 | GET | `/api/xhs/kb/list` | 列出所有 xhs_ 分区 |
| 知识库删除 | DELETE | `/api/xhs/kb/{kb_name}` | 删除指定分区 |

### 使用示例

```bash
# 普通对话
curl -X POST "http://localhost:9900/api/chat" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"你好"}'

# 流式对话
curl -X POST "http://localhost:9900/api/chat_stream" \
  -H "Content-Type: application/json" \
  -d '{"Id":"session-123","Question":"你好"}' \
  --no-buffer

# AIOps 诊断
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"session-123"}' \
  --no-buffer
```

## 📁 项目结构

```
super_biz_agent_py/
├── app/                                    # 应用核心
│   ├── __init__.py                         # 包初始化（自动加载日志配置）
│   ├── main.py                             # FastAPI 应用入口
│   ├── config.py                           # 配置管理（环境变量、MCP 服务器配置）
│   ├── api/                                # API 路由层
│   │   ├── __init__.py
│   │   ├── chat.py                         # 对话接口（RAG 聊天）
│   │   ├── aiops.py                        # AIOps 接口（故障诊断）
│   │   ├── file.py                         # 文件管理（文档上传）
│   │   └── health.py                       # 健康检查（服务状态）
│   ├── services/                           # 业务服务层
│   │   ├── __init__.py
│   │   ├── rag_agent_service.py            # RAG Agent（LangGraph 状态图）
│   │   ├── aiops_service.py                # AIOps 服务（计划-执行-重规划）
│   │   ├── vector_store_manager.py         # 向量存储管理器
│   │   ├── vector_embedding_service.py     # 向量embedding服务
│   │   ├── vector_index_service.py         # 向量索引服务
│   │   ├── vector_search_service.py        # 向量检索服务
│   │   └── document_splitter_service.py    # 文档分割服务
│   ├── agent/                              # Agent 模块
│   │   ├── __init__.py
│   │   ├── mcp_client.py                   # MCP 客户端（工具调用）
│   │   └── aiops/                          # AIOps 核心逻辑
│   │       ├── __init__.py
│   │       ├── planner.py                  # 计划制定器
│   │       ├── executor.py                 # 步骤执行器
│   │       ├── replanner.py                # 重规划器
│   │       ├── state.py                    # 状态定义
│   │       └── utils.py                    # 工具函数
│   ├── models/                             # 数据模型层
│   │   ├── __init__.py
│   │   ├── aiops.py                        # AIOps 模型
│   │   ├── document.py                     # 文档模型
│   │   ├── request.py                      # 请求模型
│   │   └── response.py                     # 响应模型
│   ├── tools/                              # Agent 工具集
│   │   ├── __init__.py
│   │   ├── knowledge_tool.py               # 知识库查询工具
│   │   └── time_tool.py                    # 时间工具
│   ├── core/                               # 核心组件
│   │   ├── __init__.py
│   │   ├── llm_factory.py                  # LLM 工厂（模型管理）
│   │   └── milvus_client.py                # Milvus 客户端
│   └── utils/                              # 工具类
│       ├── __init__.py
│       └── logger.py                       # 日志配置（Loguru）
├── static/                                 # Web 前端（纯静态）
│   ├── index.html                          # 主页面
│   ├── app.js                              # 前端逻辑
│   └── styles.css                          # 样式表
├── mcp_servers/                            # MCP 服务器
│   ├── cls_server.py                       # CLS 日志查询服务
│   ├── monitor_server.py                   # 监控数据服务
│   └── README.md                           # MCP 服务说明
├── aiops-docs/                             # 运维知识库（Markdown 文档）
├── logs/                                   # 日志目录（Loguru 自动创建）
│   └── app_YYYY-MM-DD.log                  # 按天轮转的日志文件
├── uploads/                                # 上传文件临时目录
├── volumes/                                # Milvus 数据持久化目录
├── .env                                    # 环境变量配置（需手动创建）
├── Makefile                                # 项目管理命令（Linux/macOS）
├── start-windows.bat                       # Windows 启动脚本
├── stop-windows.bat                        # Windows 停止脚本
├── vector-database.yml                     # Milvus Docker Compose 配置
├── pyproject.toml                          # 项目配置（依赖、元数据）
├── uv.lock                                 # uv 依赖锁定文件
├── pyrightconfig.json                      # Pyright 类型检查配置
└── README.md                               # 项目说明
```

## ⚙️ 配置说明

通过 `.env` 文件配置：

```bash
# 阿里云LLM DashScope 配置（必填）
# 秘钥管理： https://bailian.console.aliyun.com/cn-beijing/?spm=5176.29597918.J_SEsSjsNv72yRuRFS2VknO.2.61ac133ccTVQLw&tab=demohouse#/api-key
DASHSCOPE_API_KEY=your-api-key （配置你自己的秘钥）
DASHSCOPE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1  # 不配置则默认会使用新加坡站点
DASHSCOPE_MODEL=qwen-max

# Milvus 配置
MILVUS_HOST=localhost
MILVUS_PORT=19530

# RAG 配置
RAG_TOP_K=3
CHUNK_MAX_SIZE=800
CHUNK_OVERLAP=100

# 小红书 MCP / RAG
MCP_XHS_URL=http://localhost:8013/mcp
# XHS_COOKIE 不填则走 Mock 数据（推荐先用 Mock 跑通流程）
XHS_COOKIE=
```

## 🎯 AIOps 智能运维

基于 **Plan-Execute-Replan** 模式实现自动故障诊断。

### 核心特性
- ✅ 自动制定诊断计划（Planner）
- ✅ 智能工具调用（Executor）
- ✅ 动态调整步骤（Replanner）
- ✅ 流式输出诊断过程
- ✅ 生成结构化报告

### 快速测试

```bash
# 服务已通过 make init 自动启动
# 如需重启服务：make restart

# 访问 Web 界面，点击"智能运维与诊断工具"
# 或使用 API
curl -X POST "http://localhost:9900/api/aiops" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"test"}' \
  --no-buffer
```

### 诊断流程
```
1. Planner 制定计划 → 生成 4-6 个诊断步骤
2. Executor 执行步骤 → 调用 MCP 工具（日志查询、监控数据）
3. Replanner 评估结果 → 决定继续/调整/生成报告
4. 输出诊断报告 → 根因分析 + 运维建议
```

## 📝 开发指南

### 常用命令

```bash
# 项目管理
make init              # 一键初始化（Docker + 服务 + 文档）
make start             # 启动所有服务
make stop              # 停止所有服务
make restart           # 重启所有服务

# 依赖管理
make install-dev       # 安装开发依赖
make sync              # 同步依赖

# Docker 管理
make up                # 启动 Docker 容器
make down              # 停止 Docker 容器

# 代码质量
make format            # 格式化代码
make lint              # 代码检查
```


## 🐛 常见问题

### Windows 环境问题

#### 1. `make` 命令不可用
Windows 不支持 `make` 命令，请使用提供的批处理脚本：
```powershell
# 启动服务
.\start-windows.bat

# 停止服务
.\stop-windows.bat
```

#### 2. PowerShell 执行策略限制
如果遇到 "无法加载文件，因为在此系统上禁止运行脚本" 错误：
```powershell
# 临时允许脚本执行（管理员权限）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 或者使用 CMD 而不是 PowerShell
cmd
.\start-windows.bat
```

#### 3. 端口被占用（Windows）
```powershell
# 查看占用端口的进程
netstat -ano | findstr :9900

# 结束进程（替换 PID 为实际进程 ID）
taskkill /F /PID <PID>
```

### 通用问题

### API Key 错误
```bash
# 检查环境变量
cat .env | grep DASHSCOPE_API_KEY    # Linux/macOS
type .env | findstr DASHSCOPE_API_KEY  # Windows
```

### Milvus 连接失败
```bash
# 确保本机有 Docker 服务并且已经启动（可以使用 Docker Desktop）

# 检查 Milvus 状态
docker ps | grep milvus

# 重启 Milvus（使用 docker compose）
docker compose -f vector-database.yml restart

# 或者重启单个服务
docker compose -f vector-database.yml restart standalone
```

### 服务无法启动

**Linux/macOS:**
```bash
# 查看服务日志
tail -f logs/app_$(date +%Y-%m-%d).log  # FastAPI 主服务（Loguru 日志）
tail -f mcp_cls.log                      # CLS MCP 服务
tail -f mcp_monitor.log                  # Monitor MCP 服务

# 检查端口占用
lsof -i :9900  # FastAPI
lsof -i :8003  # CLS MCP
lsof -i :8004  # Monitor MCP
```

**Windows:**
```powershell
# 查看服务日志（获取今天的日期）
$today = Get-Date -Format "yyyy-MM-dd"
type logs\app_$today.log  # FastAPI 主服务（Loguru 日志）
type mcp_cls.log          # CLS MCP 服务
type mcp_monitor.log      # Monitor MCP 服务

# 或者查看最新的日志文件
Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1 | Get-Content -Tail 50

# 检查端口占用
netstat -ano | findstr :9900  # FastAPI
netstat -ano | findstr :8003  # CLS MCP
netstat -ano | findstr :8004  # Monitor MCP
```

## 📚 参考资源

- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [LangChain 文档](https://python.langchain.com/)
- [LangGraph Plan-Execute](https://langchain-ai.github.io/langgraph/tutorials/plan-and-execute/)
- [阿里云 DashScope](https://dashscope.aliyun.com/)
- [MCP 协议](https://modelcontextprotocol.io/)

## 📕 小红书 RAG（动态知识库）

把小红书旅游攻略**按需**抓进 Milvus，每次搜索建一个独立分区（KB），聊天时**手动**指定 `kb_name` 让 LLM 基于该分区检索作答。

### 设计要点

- **Milvus 原生 Partition 隔离**：每次入库一个 `xhs_<md5前8>_<时间戳>` 分区，互不污染
- **手动开关**：原 `/api/chat` 不变；走 RAG 必须用 `/api/chat/rag` 或 `/api/chat/rag_stream`，且**必填 `kb_name`**
- **Mock 模式**：不配 `XHS_COOKIE` 时 MCP 返回内置 mock 笔记（成都/北京/深圳），可直接跑通整条链路
- **会话共享**：同一 `session_id` 在 `/chat` 与 `/chat/rag` 间历史是连续的

### 启动流程（Windows / PowerShell）

按顺序开 3 个 PowerShell 窗口，**每个窗口都要先激活 venv**（`.venv\Scripts\activate`）。

```powershell
# 窗口 1 — Milvus（已通过 docker compose 起好则跳过）
docker compose -f vector-database.yml up -d

# 窗口 2 — 小红书 MCP Server（端口 8013）
python mcp_servers/xhs_server.py
# 看到 "Uvicorn running on http://0.0.0.0:8013" 即成功

# 窗口 3 — FastAPI 主服务（端口 9900）
python -m uvicorn app.main:app --host 0.0.0.0 --port 9900
# 看到 collection 'biz' 已加载 即成功
```

启动好后访问 http://localhost:9900/docs，在 **"小红书 RAG"** 与 **"RAG 对话"** 两个 tag 下能看到全部新接口。

### 端到端冒烟测试（curl）

```powershell
# 1. 用 MCP 搜索"成都美食"，自动建分区并入库
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp `
  -H "Content-Type: application/json" `
  -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'
# 返回里记下 data.kb_name —— 后面要用

# 2. 看看现在有哪些知识库
curl.exe http://localhost:9900/api/xhs/kb/list

# 3. 用上一步的 kb_name 做 RAG 对话
curl.exe -X POST http://localhost:9900/api/chat/rag `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"成都必吃美食推荐\",\"session_id\":\"smoke-1\",\"kb_name\":\"<填这里>\"}'
# 返回的 answer 应该出现"郫县豆瓣鱼/夫妻肺片"等 mock 数据里的内容
# 同时 citations 字段会带笔记 title/url/author/likes

# 4. SSE 流式版（看实时打字效果）
curl.exe -N -X POST http://localhost:9900/api/chat/rag_stream `
  -H "Content-Type: application/json" `
  -d '{\"Question\":\"成都3日游怎么安排\",\"session_id\":\"smoke-2\",\"kb_name\":\"<填这里>\"}'

# 5. 不再需要时删掉知识库
curl.exe -X DELETE http://localhost:9900/api/xhs/kb/<填 kb_name>
```

### kb_name 规则

- 自动生成：`xhs_<md5(keyword|city)前8位>_<YYYYMMDD>_<HHMMSS>`
- 手动入库 `/xhs/ingest/text` 可传自定义 `kb_name`，**必须**匹配 `^xhs_[a-zA-Z0-9_]{1,240}$`，否则 400
- 不传则默认 `xhs_manual_<时间戳>`

### 切换到真实抓取

默认是 Mock 模式，足够把流程跑通。要切真实抓取：

1. 浏览器登录 https://www.xiaohongshu.com ，打开开发者工具复制完整 Cookie
2. 把 Cookie 写入 `.env` 的 `XHS_COOKIE=...`
3. 重启窗口 2（`xhs_server.py`）
4. 之后调 `/xhs/ingest/mcp` 时 response 的 `source` 字段会是 `"realtime"` 而非 `"mock"`

> ⚠️ 小红书有反爬，Cookie 可能几小时就失效；接口风格也可能变。Mock 模式始终可用。

### 故障排查

| 症状 | 原因 / 处理 |
|---|---|
| `/xhs/ingest/mcp` 返回 `MCP 连接失败` | 窗口 2 没起，或端口 8013 被占 |
| `/chat/rag` 返 404 | `kb_name` 不存在 —— 先调 `/xhs/kb/list` 看真实分区名 |
| `/chat/rag` 返 400 `kb_name 必填` | 请求体里漏了 `kb_name` 字段 |
| LLM 输出"以下为通用建议" | 该分区没检索到相关内容，是设计预期（不报错） |
| 真实模式下没结果 | XHS_COOKIE 过期或被风控，回到 Mock 模式调试 |

### 自动化测试

```powershell
# 全量单元测试（不需要 Milvus）
python -m pytest tests/ -v --no-cov

# Milvus 集成测试（需要 Milvus 在 19530 跑着）
$env:RUN_MILVUS_TESTS="1"; python -m pytest tests/services/test_vector_store_partition_integration.py -v --no-cov
```

## 📄 许可证
author： chief

MIT License
