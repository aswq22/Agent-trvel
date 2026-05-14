# 小红书动态 RAG 知识库 — 设计文档

- **日期**：2026-05-14
- **状态**：设计已批准，待生成实施计划
- **关联**：
  - 现有基础：`mcp_servers/xhs_server.py`、`app/services/xhs_ingestion_service.py`、`app/api/xhs.py`（未注册到 main.py）
  - 现有基建：`app/core/milvus_client.py`（biz collection，1024 维，IVF_FLAT/L2）
  - 现有聊天：`app/api/chat.py`（纯 LLM，无 RAG）

## 1. 目标与非目标

### 目标

1. 用户可以基于小红书搜索结果**动态地**建立向量知识库，每次搜索独立成库
2. 用户在聊天时**手动选择**是否启用 RAG，以及查询哪个知识库
3. 提供知识库的列表与删除能力
4. 聊天返回中携带引用来源（小红书笔记标题/URL/作者/点赞数）

### 非目标

- LLM 自动判断是否触发 RAG（agentic / tool-calling）
- 真实小红书反爬抓取的稳定性（沿用现有 `xhs_server.py` 的 cookie 模式 + mock fallback）
- 知识库的版本管理、增量更新、跨库联合检索
- 旅游 Agent（六 Agent 子图）接入 RAG —— 本期仅改 `/chat`
- 知识库 LRU 内存释放策略

## 2. 用户决策（已对齐）

| 维度 | 决策 |
|---|---|
| RAG 触发方式 | 用户手动选择（请求里指定 kb_name） |
| 建库粒度 | 按会话/任务分区，可切换 |
| MCP 来源 | 沿用项目内现有 `mcp_servers/xhs_server.py` |
| kb_name 来源 | 自动生成（哈希 + 时间戳） |
| 管理接口 | 需要 `list` + `delete` |
| 返回形式 | SSE 流式 + 携带引用来源 |
| Milvus 隔离方式 | 原生 Partition |

## 3. 总体架构

三条独立链路：

### 链路 A — 动态建库

```
POST /api/xhs/ingest/mcp { keyword, city, count }
   → xhs_ingestion_service.ingest_from_mcp()
       1. fastmcp Client 调 xhs_server (8013) 拿 notes[]
       2. _make_kb_name() 生成 partition 名
       3. RecursiveCharacterTextSplitter 切块
       4. vector_store_manager.ensure_partition(kb_name)
       5. vector_store_manager.add_documents_to_partition(docs, kb_name)
   → Milvus biz collection / partition[kb_name]
   ← { kb_name, ingested, chunks }
```

### 链路 B — RAG 对话

```
POST /api/chat/rag (或 /chat/rag_stream)
   { Question, session_id, kb_name, top_k? }
   → rag_service.build_rag_context()
       1. similarity_search_in_partition(query, kb_name, k=top_k)
       2. 拼接 system_prompt with 参考资料
       3. 构造 messages = [system, ...history[-20:], human]
       4. 提取 citations（按 note_id 去重）
   → LLMFactory.create_travel_llm().ainvoke / astream
   → session_store.append
   ← { answer, citations, hit_count }
```

### 链路 C — 知识库管理

```
GET    /api/xhs/kb/list           → collection.partitions, 过滤 xhs_ 前缀
DELETE /api/xhs/kb/{kb_name}      → partition.release() → drop_partition
```

## 4. API 协议

所有接口挂载在 `/api` 前缀（与现有 `chat`、`travel` 一致）。

### 4.1 入库

**`POST /api/xhs/ingest/mcp`**（修改）

```jsonc
// Request
{ "keyword": "美食攻略", "city": "成都", "count": 10 }
// Response 200
{
  "code": 200,
  "data": {
    "kb_name": "xhs_a3f9c1b2_20260514_153021",  // 新增
    "ingested": 10,
    "chunks": 47,
    "keyword": "美食攻略",
    "city": "成都"
  }
}
// 0 笔记时：data.kb_name = null，不创建 partition
```

**`POST /api/xhs/ingest/text`**（修改）

```jsonc
// Request 增加可选 kb_name
{ "title":"...", "content":"...", "city":"", "tags":[], "kb_name":"" }
// 不传 kb_name 时默认 "xhs_manual_{YYYYMMDD_HHMMSS}"
// 用户传入的 kb_name 必须满足 ^xhs_[a-zA-Z0-9_]{1,240}$ 且未以 _default 开头，否则 400
```

### 4.2 知识库管理

**`GET /api/xhs/kb/list`**（新增）

```jsonc
{
  "code": 200,
  "data": {
    "total": 3,
    "kbs": [
      { "kb_name": "xhs_a3f9c1b2_20260514_153021",
        "num_entities": 47,
        "description": "美食攻略|成都",
        "created_at": "2026-05-14 15:30:21" }
    ]
  }
}
```

`description` 来自 `create_partition` 时存的 `keyword|city`；`created_at` 从 kb_name 末尾时间戳解析。

**`DELETE /api/xhs/kb/{kb_name}`**（新增）

```jsonc
// 200
{ "code": 200, "data": { "kb_name": "...", "deleted_entities": 47 } }
// 404
{ "code": 404, "message": "partition not found", "data": null }
```

**`GET /api/xhs/stats`**（保留不变）

### 4.3 RAG 对话

**`POST /api/chat/rag`**（新增）

```jsonc
// Request
{
  "Question": "在成都玩 3 天怎么安排？",
  "session_id": "user-123",
  "kb_name": "xhs_a3f9c1b2_20260514_153021",
  "top_k": 3
}
// Response 200
{
  "code": 200,
  "data": {
    "success": true,
    "answer": "根据小红书攻略，建议...",
    "citations": [
      { "title": "成都5天4夜深度游攻略", "url": "https://...",
        "author": "旅行达人小王", "likes": 8832 }
    ],
    "hit_count": 3,
    "errorMessage": null
  }
}
// 400: kb_name 缺失
// 404: kb_name 对应 partition 不存在
```

**`POST /api/chat/rag_stream`**（新增，SSE）

```
data: {"type":"citations","data":[{...}, {...}]}
data: {"type":"content","data":"根据"}
data: {"type":"content","data":"小红书攻略"}
...
data: {"type":"done"}
// 异常：data: {"type":"error","data":"..."}
```

引用事件**先于内容事件**推送，便于前端先渲染引用卡片。

## 5. 命名规则

```python
def _make_kb_name(keyword: str, city: str) -> str:
    seed = f"{keyword}|{city}".encode()
    short = hashlib.md5(seed).hexdigest()[:8]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"xhs_{short}_{ts}"
# 例：xhs_a3f9c1b2_20260514_153021
```

约束：

- Milvus partition 名只允许字母/数字/下划线，最长 255 字符 — 上述格式始终满足
- 同 keyword+city 不同时刻多次入库，会产生不同 kb_name（不合并），列表里可见
- 不引入 pypinyin（第一版 YAGNI），keyword 信息存 partition `description`

## 6. VectorStoreManager 改造

新增 5 个方法到 `app/services/vector_store_manager.py`，旧 API 不破坏：

```python
def ensure_partition(self, kb_name: str, description: str = "") -> None
def add_documents_to_partition(self, docs: list[Document], kb_name: str) -> list[str]
def similarity_search_in_partition(self, query: str, kb_name: str, k: int = 3) -> list[Document]
def list_kb_partitions(self) -> list[dict]      # 过滤 xhs_ 前缀
def drop_kb_partition(self, kb_name: str) -> int  # 不存在返 -1
```

实现要点：

- LangChain `Milvus.add_documents` 不暴露 partition_name，因此 **写入与检索均直接走 pymilvus 原生 API**：
  - embedding 复用 `vector_embedding_service.embed_documents` / `embed_query`
  - 写入：`collection.insert([ids, vectors, texts, metadatas], partition_name=kb_name)`，随后 `collection.flush()` 立即可查
  - 检索：`collection.search(data=[qv], anns_field="vector", param={"metric_type":"L2","params":{"nprobe":16}}, limit=k, partition_names=[kb_name], output_fields=["content","metadata"])`
- `ensure_partition` 幂等：`if not collection.has_partition(kb_name): collection.create_partition(kb_name, description)`
- 新 partition 创建后**手动调用 `partition.load()`**，否则不在内存中、无法检索
- `drop_kb_partition` 先 `release()` 再 `drop_partition`，否则 Milvus 会拒绝
- 旧的 `add_documents` / `similarity_search` 保留语义不变（等价于操作 `_default` 分区）

## 7. RAG Service

`app/services/rag_service.py`（新文件）。单一职责：构造 RAG 上下文，不耦合 FastAPI / LLM。

```python
@dataclass
class Citation:
    title: str
    url: str
    author: str
    likes: int

@dataclass
class RagContext:
    messages: list[BaseMessage]
    citations: list[Citation]
    hit_count: int

def build_rag_context(
    question: str,
    history: list[dict],
    kb_name: str,
    top_k: int = 3,
) -> RagContext:
    ...
```

### Prompt 模板

```
你是一个智能旅游助手。请基于下面的小红书攻略参考资料回答用户问题。
- 优先使用参考资料中的信息
- 如果参考资料不足，可以基于通用常识补充，但要明确标注"以下为通用建议"
- 不要编造资料里没有的具体地名/价格/路线

【参考资料】
[1] 标题：{md.file_name}（作者：{md.author}，{md.likes} 赞）
    内容：{doc.page_content}
[2] ...
```

### Citations 去重

同一 `note_id` 只保留首次出现的一条（同一条笔记被切成多个 chunk 时，避免前端展示重复）。

### 命中为空

`docs == []` 时仍正常走 LLM，`system_prompt` 改为提示"未检索到相关攻略，以下为通用建议"，`citations=[]`，`hit_count=0`。**不**抛错。

## 8. Session Store 抽离

将 `app/api/chat.py` 中模块私有的 `_sessions: dict[str, list]` 抽到 `app/services/session_store.py`，提供：

```python
def get(sid: str) -> list[dict]
def append(sid: str, role: str, content: str) -> None
def clear(sid: str) -> None
```

`chat.py`、`chat_rag.py` 共享此 store —— 用户同一 `session_id` 在 `/chat` 与 `/chat/rag` 间切换时，**历史连续**（是 feature，不是 bug）。

## 9. 错误处理矩阵

| 情形 | HTTP / 事件 | 行为 |
|---|---|---|
| `kb_name` 请求未传 | 400 / `error` | 提示 "kb_name 必填" |
| `kb_name` 对应 partition 不存在 | 404 / `error` | `similarity_search_in_partition` 先 `has_partition` 检查，抛 `KBNotFoundError` |
| 检索命中 0 条 | 200 | 仍走 LLM，prompt 改写，`citations=[]` |
| Embedding 失败（DashScope 4xx/5xx） | 500 / `error` | loguru 记录，错误信息回传 |
| Milvus 连接断开 | 500 | 同上 |
| LLM 调用失败 | 500 | 同上 |
| `/xhs/ingest/mcp` 拿到 0 条笔记 | 200 | 返回 `kb_name=null, ingested=0`，**不创建空 partition** |
| 入库时 partition 已存在 | 200 | `ensure_partition` 幂等，追加而非覆盖 |
| `DELETE /xhs/kb/{name}` name 不存在 | 404 | 返回 message 提示 |

## 10. 文件改动清单

| 文件 | 改动类型 | 内容 |
|---|---|---|
| `mcp_servers/xhs_server.py` | 不变 | 沿用 |
| `app/services/xhs_ingestion_service.py` | 修改 | 加 `_make_kb_name`；`ingest_notes` 改走 `add_documents_to_partition` |
| `app/services/vector_store_manager.py` | 修改 | 新增 5 个 partition 方法（见 §6） |
| `app/services/rag_service.py` | 新建 | `Citation` / `RagContext` / `build_rag_context` |
| `app/services/session_store.py` | 新建 | 抽离 `_sessions` |
| `app/api/xhs.py` | 修改 | `ingest_mcp` 返回 kb_name；新增 `kb/list`、`kb/{name}` (DELETE) |
| `app/api/chat.py` | 修改 | 用 `session_store` 替换私有字典 |
| `app/api/chat_rag.py` | 新建 | `/chat/rag` + `/chat/rag_stream` |
| `app/main.py` | 修改 | 注册 `xhs.router` 和 `chat_rag.router`（xhs 路由当前未挂载 —— 顺手补） |

## 11. 测试策略

### 11.1 单元测试（mock 全部外部依赖；CI 跑）

| 文件 | 覆盖 |
|---|---|
| `tests/services/test_xhs_ingestion_service.py` | `_make_kb_name` 格式；空 city；0 笔记不创建 partition |
| `tests/services/test_rag_service.py` | 检索结果拼接；citations 按 note_id 去重；空命中 fallback prompt；history 截 20 条 |
| `tests/api/test_xhs_api.py` | `ingest_mcp` 返 kb_name；`kb/list` 过滤前缀；`DELETE` 404 路径 |
| `tests/api/test_chat_rag_api.py` | 正常路径 answer+citations；kb_name 不存在返 404；SSE 首事件 citations、末事件 done |

### 11.2 集成测试（连真 Milvus，可选跳过）

`tests/services/test_vector_store_partition.py` — `@pytest.mark.skipif(not os.getenv("MILVUS_HOST"))`：

- `ensure_partition` 幂等
- 跨分区隔离（partition A 内容不出现在 B 的检索结果）
- `drop_kb_partition` 后 list 消失
- teardown 必须清理测试 partition

### 11.3 端到端手测清单

实施完成后由用户手动验证：

1. 启动 `mcp_servers/xhs_server.py`（端口 8013）+ `app/main.py`
2. `POST /api/xhs/ingest/mcp { "keyword":"美食", "city":"成都", "count":5 }` → 拿到 `kb_name`
3. `GET /api/xhs/kb/list` → 看到该 kb
4. `POST /api/chat/rag { "Question":"成都必吃美食?", "kb_name":"<上一步>" }` → 返回应含 mock 数据中"郫县豆瓣鱼/夫妻肺片"
5. `POST /api/chat/rag_stream` 同上但 SSE
6. 错误 `kb_name` → 404
7. `DELETE /api/xhs/kb/{name}` → list 消失
8. 原 `POST /api/chat`（无 RAG）正常工作，不受影响

## 12. 风险与权衡

- **每个 partition 常驻内存**：本期接受。KB > 50 时再做 LRU。
- **kb_name 不可读**：用 `description` 字段补足；前端列表展示时同时显示 description。
- **MD5 8 位短哈希**：碰撞概率极低（且时间戳兜底），不引入复杂度。
- **跨库联合检索**：本期不支持。如有需求，后续可在 `similarity_search_in_partition` 上扩展 `partition_names: list[str]`。
