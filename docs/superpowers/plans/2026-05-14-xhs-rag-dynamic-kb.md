# 小红书动态 RAG 知识库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让用户能通过小红书 MCP 动态建立 Milvus 分区向量库，并在聊天中显式选择是否启用 RAG 检索。

**Architecture:** 在已有的 Milvus `biz` collection 下使用原生 Partition 隔离每次入库结果。新增 `vector_store_manager` 的 partition 操作方法，抽离 `rag_service` 负责检索+prompt 构造+citations。聊天侧新增 `/api/chat/rag`（阻塞）和 `/api/chat/rag_stream`（SSE），与原 `/chat` 并存。

**Tech Stack:** FastAPI + pymilvus 原生 Partition API + LangChain Documents + DashScope embedding（已有的 `vector_embedding_service`）+ DeepSeek LLM（已有的 `LLMFactory.create_travel_llm`）+ pytest/pytest-asyncio。

**Spec:** `docs/superpowers/specs/2026-05-14-xhs-rag-dynamic-kb-design.md`

---

## 文件结构

**新建：**
- `app/services/session_store.py` — 共享会话存储
- `app/services/rag_service.py` — RAG 上下文构造（检索 + prompt + citations 去重）
- `app/api/chat_rag.py` — `/chat/rag` + `/chat/rag_stream`
- `tests/services/__init__.py`
- `tests/services/test_session_store.py`
- `tests/services/test_xhs_ingestion_service.py`
- `tests/services/test_rag_service.py`
- `tests/services/test_vector_store_partition.py`（集成测试，需 Milvus）
- `tests/api/test_xhs_api.py`
- `tests/api/test_chat_rag_api.py`

**修改：**
- `app/services/vector_store_manager.py` — 新增 5 个 partition 方法
- `app/services/xhs_ingestion_service.py` — 自动生成 kb_name，走 partition
- `app/api/xhs.py` — ingest 返回 kb_name；新增 list/delete；校验手传 kb_name
- `app/api/chat.py` — 用 `session_store` 替换私有 `_sessions`
- `app/main.py` — 注册 `xhs.router` 和 `chat_rag.router`

---

## Task 1: 抽离 Session Store 并重构 chat.py

**Files:**
- Create: `app/services/session_store.py`
- Create: `tests/services/__init__.py`
- Create: `tests/services/test_session_store.py`
- Modify: `app/api/chat.py`

- [ ] **Step 1.1: 创建测试目录占位**

写 `tests/services/__init__.py`（空文件）。

- [ ] **Step 1.2: 写 session_store 失败测试**

`tests/services/test_session_store.py`：

```python
"""tests for session_store module"""

from app.services import session_store


def setup_function(_):
    """每个测试前清空全局状态"""
    session_store._sessions.clear()


def test_get_empty_session_returns_empty_list():
    assert session_store.get("nonexistent") == []


def test_append_then_get():
    session_store.append("s1", "user", "hi")
    session_store.append("s1", "assistant", "hello")
    history = session_store.get("s1")
    assert history == [
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]


def test_clear_removes_session():
    session_store.append("s1", "user", "hi")
    session_store.clear("s1")
    assert session_store.get("s1") == []


def test_clear_nonexistent_is_noop():
    session_store.clear("never-existed")  # 不抛错
    assert session_store.get("never-existed") == []


def test_sessions_are_isolated():
    session_store.append("a", "user", "hi-a")
    session_store.append("b", "user", "hi-b")
    assert session_store.get("a") == [{"role": "user", "content": "hi-a"}]
    assert session_store.get("b") == [{"role": "user", "content": "hi-b"}]
```

- [ ] **Step 1.3: 跑测试确认失败**

Run: `pytest tests/services/test_session_store.py -v`
Expected: ImportError / ModuleNotFoundError (`app.services.session_store` 不存在)

- [ ] **Step 1.4: 实现 session_store**

`app/services/session_store.py`：

```python
"""共享会话存储 — chat 与 chat_rag 共用。

注意：进程内存储，进程重启后会话丢失（本期接受）。
"""
from typing import Dict, List

_sessions: Dict[str, List[dict]] = {}


def get(sid: str) -> List[dict]:
    """读取会话历史；不存在时返回空列表（不写回）。"""
    return _sessions.get(sid, [])


def append(sid: str, role: str, content: str) -> None:
    """追加一条消息到会话历史。"""
    _sessions.setdefault(sid, []).append({"role": role, "content": content})


def clear(sid: str) -> None:
    """清空指定会话；不存在时静默返回。"""
    _sessions.pop(sid, None)
```

- [ ] **Step 1.5: 跑测试确认通过**

Run: `pytest tests/services/test_session_store.py -v`
Expected: 5 passed

- [ ] **Step 1.6: 重构 chat.py 使用 session_store**

修改 `app/api/chat.py`，把模块顶部的 `_sessions: Dict[str, List[dict]] = {}` 删除，并将所有引用 `_sessions` 的地方替换：

```python
"""聊天 API — 基于 LLMFactory 的简单对话接口"""

import json
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel

from app.core.llm_factory import LLMFactory
from app.services import session_store

router = APIRouter()

_SYSTEM_PROMPT = (
    "你是一个智能旅游助手，也可以回答各种日常问题。"
    "请用友好、简洁的方式用中文回复用户。"
)


class ChatRequest(BaseModel):
    Id: str = ""
    Question: str = ""
    session_id: Optional[str] = None
    message: Optional[str] = None


class ClearRequest(BaseModel):
    session_id: str = ""
    sessionId: str = ""


def _sid(req: ChatRequest) -> str:
    return req.Id or req.session_id or "default"


def _question(req: ChatRequest) -> str:
    return req.Question or req.message or ""


def _build_lc_messages(history: List[dict], question: str):
    msgs: list = [SystemMessage(content=_SYSTEM_PROMPT)]
    for h in history[-20:]:
        if h["role"] == "user":
            msgs.append(HumanMessage(content=h["content"]))
        else:
            msgs.append(AIMessage(content=h["content"]))
    msgs.append(HumanMessage(content=question))
    return msgs


def _make_llm(streaming: bool = False):
    return LLMFactory.create_travel_llm(temperature=0.7, streaming=streaming)


@router.post("/chat")
async def chat(request: ChatRequest):
    sid = _sid(request)
    q = _question(request)
    if not q:
        return {"code": 400, "message": "问题不能为空", "data": None}

    history = session_store.get(sid)
    msgs = _build_lc_messages(history, q)

    try:
        response = await _make_llm().ainvoke(msgs)
        answer = response.content
        session_store.append(sid, "user", q)
        session_store.append(sid, "assistant", answer)
        return {
            "code": 200,
            "message": "success",
            "data": {"success": True, "answer": answer, "errorMessage": None},
        }
    except Exception as e:
        logger.exception("chat error: {}", repr(e))
        return {
            "code": 500,
            "message": str(e),
            "data": {"success": False, "answer": None, "errorMessage": str(e)},
        }


@router.post("/chat_stream")
async def chat_stream(request: ChatRequest):
    sid = _sid(request)
    q = _question(request)
    history = session_store.get(sid)
    msgs = _build_lc_messages(history, q)

    async def generate():
        full_response = ""
        try:
            async for chunk in _make_llm(streaming=True).astream(msgs):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    full_response += content
                    payload = json.dumps({"type": "content", "data": content}, ensure_ascii=False)
                    yield f"data: {payload}\n\n"
            session_store.append(sid, "user", q)
            session_store.append(sid, "assistant", full_response)
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("chat_stream error: {}", repr(e))
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/chat/session/{session_id}")
async def get_session(session_id: str):
    history = session_store.get(session_id)
    return {"history": history, "session_id": session_id, "message_count": len(history)}


@router.post("/chat/clear")
async def clear_session(request: ClearRequest):
    sid = request.session_id or request.sessionId
    session_store.clear(sid)
    return {"status": "success", "message": "会话已清空"}
```

- [ ] **Step 1.7: 跑全部 chat 相关测试，确认未破坏**

Run: `pytest tests/services/test_session_store.py tests/api/ -v`
Expected: session_store 5 passed；其它测试不变。

- [ ] **Step 1.8: Commit**

```bash
git add app/services/session_store.py app/api/chat.py tests/services/__init__.py tests/services/test_session_store.py
git commit -m "refactor(chat): extract _sessions into shared session_store module"
```

---

## Task 2: VectorStoreManager 加 partition 方法（ensure / list / drop）

**Files:**
- Modify: `app/services/vector_store_manager.py`
- Create: `tests/services/test_vector_store_manager_partition.py`

注：本 task 仅实现「不需要 embedding」的 3 个方法（ensure / list / drop），用 mock collection 跑单元测试。`add_documents_to_partition` 和 `similarity_search_in_partition` 在 Task 3 实现（涉及 embedding，单测代码不同）。

- [ ] **Step 2.1: 写失败测试**

`tests/services/test_vector_store_manager_partition.py`：

```python
"""单元测试：VectorStoreManager 的 partition 管理方法（mock collection）"""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def fake_collection():
    """模拟 pymilvus Collection。"""
    coll = MagicMock()
    coll.has_partition = MagicMock(return_value=False)
    coll.create_partition = MagicMock()
    return coll


@pytest.fixture
def vsm(fake_collection):
    """patch milvus_manager 后导入 vector_store_manager 单例。"""
    with patch("app.services.vector_store_manager.milvus_manager") as mm:
        mm.get_collection.return_value = fake_collection
        from app.services.vector_store_manager import vector_store_manager
        yield vector_store_manager


def test_ensure_partition_creates_when_missing(vsm, fake_collection):
    fake_collection.has_partition.return_value = False
    vsm.ensure_partition("xhs_abc_20260514", description="美食|成都")
    fake_collection.create_partition.assert_called_once_with(
        partition_name="xhs_abc_20260514", description="美食|成都"
    )


def test_ensure_partition_idempotent(vsm, fake_collection):
    fake_collection.has_partition.return_value = True
    vsm.ensure_partition("xhs_abc_20260514")
    fake_collection.create_partition.assert_not_called()


def test_list_kb_partitions_filters_xhs_prefix(vsm, fake_collection):
    p_xhs = MagicMock(name="xhs_abc_20260514", num_entities=42, description="美食|成都")
    p_xhs.name = "xhs_abc_20260514"
    p_default = MagicMock(num_entities=100)
    p_default.name = "_default"
    fake_collection.partitions = [p_default, p_xhs]

    result = vsm.list_kb_partitions()
    assert len(result) == 1
    assert result[0]["kb_name"] == "xhs_abc_20260514"
    assert result[0]["num_entities"] == 42
    assert result[0]["description"] == "美食|成都"


def test_drop_kb_partition_not_found_returns_minus_one(vsm, fake_collection):
    fake_collection.has_partition.return_value = False
    assert vsm.drop_kb_partition("xhs_missing") == -1


def test_drop_kb_partition_releases_then_drops(vsm, fake_collection):
    fake_collection.has_partition.return_value = True
    fake_partition = MagicMock(num_entities=47)
    fake_collection.partition.return_value = fake_partition

    result = vsm.drop_kb_partition("xhs_abc_20260514")

    assert result == 47
    fake_partition.release.assert_called_once()
    fake_collection.drop_partition.assert_called_once_with("xhs_abc_20260514")
```

- [ ] **Step 2.2: 跑测试确认失败**

Run: `pytest tests/services/test_vector_store_manager_partition.py -v`
Expected: AttributeError（方法不存在）

- [ ] **Step 2.3: 实现 3 个方法**

在 `app/services/vector_store_manager.py` 的 `VectorStoreManager` 类内，`similarity_search` 方法之后追加：

```python
    # ── Partition operations (XHS RAG) ─────────────────────────────────

    def ensure_partition(self, kb_name: str, description: str = "") -> None:
        """幂等创建 partition。已存在则跳过。"""
        collection = milvus_manager.get_collection()
        if collection.has_partition(kb_name):
            logger.debug(f"partition '{kb_name}' 已存在")
            return
        collection.create_partition(
            partition_name=kb_name,
            description=description,
        )
        logger.info(f"创建 partition '{kb_name}', description='{description}'")

    def list_kb_partitions(self) -> List[dict]:
        """列出所有 xhs_ 前缀的 partition。"""
        collection = milvus_manager.get_collection()
        result: List[dict] = []
        for p in collection.partitions:
            if not p.name.startswith("xhs_"):
                continue
            result.append({
                "kb_name": p.name,
                "num_entities": p.num_entities,
                "description": getattr(p, "description", "") or "",
            })
        return result

    def drop_kb_partition(self, kb_name: str) -> int:
        """删除 partition；不存在返回 -1，否则返回被删向量数。"""
        collection = milvus_manager.get_collection()
        if not collection.has_partition(kb_name):
            return -1
        partition = collection.partition(kb_name)
        n = partition.num_entities
        try:
            partition.release()
        except Exception as e:
            logger.warning(f"release partition '{kb_name}' 失败（可能未加载）: {e}")
        collection.drop_partition(kb_name)
        logger.info(f"删除 partition '{kb_name}', 释放 {n} 向量")
        return n
```

- [ ] **Step 2.4: 跑测试确认通过**

Run: `pytest tests/services/test_vector_store_manager_partition.py -v`
Expected: 5 passed

- [ ] **Step 2.5: Commit**

```bash
git add app/services/vector_store_manager.py tests/services/test_vector_store_manager_partition.py
git commit -m "feat(vector-store): add ensure/list/drop partition methods for XHS RAG"
```

---

## Task 3: VectorStoreManager.add_documents_to_partition + similarity_search_in_partition

**Files:**
- Modify: `app/services/vector_store_manager.py`
- Modify: `tests/services/test_vector_store_manager_partition.py`

- [ ] **Step 3.1: 追加失败测试**

在 `tests/services/test_vector_store_manager_partition.py` 末尾追加：

```python
from langchain_core.documents import Document


def test_add_documents_to_partition_inserts_with_partition_name(vsm, fake_collection):
    fake_collection.has_partition.return_value = True
    docs = [
        Document(page_content="text-A", metadata={"k": "v1"}),
        Document(page_content="text-B", metadata={"k": "v2"}),
    ]
    with patch("app.services.vector_store_manager.vector_embedding_service") as emb:
        emb.embed_documents.return_value = [[0.1] * 1024, [0.2] * 1024]
        ids = vsm.add_documents_to_partition(docs, "xhs_abc_20260514")

    assert len(ids) == 2
    # 检查 insert 调用：data 是 list of columns，partition_name 正确
    insert_call = fake_collection.insert.call_args
    assert insert_call.kwargs["partition_name"] == "xhs_abc_20260514"
    columns = insert_call.kwargs["data"] if "data" in insert_call.kwargs else insert_call.args[0]
    # [ids, vectors, texts, metadatas]
    assert columns[2] == ["text-A", "text-B"]
    assert columns[3] == [{"k": "v1"}, {"k": "v2"}]


def test_add_documents_to_partition_empty_returns_empty(vsm, fake_collection):
    fake_collection.has_partition.return_value = True
    with patch("app.services.vector_store_manager.vector_embedding_service") as emb:
        ids = vsm.add_documents_to_partition([], "xhs_abc_20260514")
    assert ids == []
    fake_collection.insert.assert_not_called()


def test_similarity_search_in_partition_passes_partition_name(vsm, fake_collection):
    fake_collection.has_partition.return_value = True
    # 构造 search 返回结构：results[0] 是 hits 列表
    hit = MagicMock()
    hit.entity.get = lambda field, default=None: {
        "content": "text-A", "metadata": {"k": "v1"}
    }.get(field, default)
    fake_collection.search.return_value = [[hit]]

    fake_partition = MagicMock()
    fake_collection.partition.return_value = fake_partition

    with patch("app.services.vector_store_manager.vector_embedding_service") as emb:
        emb.embed_query.return_value = [0.5] * 1024
        results = vsm.similarity_search_in_partition("query", "xhs_abc_20260514", k=3)

    fake_partition.load.assert_called_once()
    call = fake_collection.search.call_args
    assert call.kwargs["partition_names"] == ["xhs_abc_20260514"]
    assert call.kwargs["limit"] == 3
    assert call.kwargs["output_fields"] == ["content", "metadata"]
    assert len(results) == 1
    assert results[0].page_content == "text-A"
    assert results[0].metadata == {"k": "v1"}


def test_similarity_search_in_partition_missing_raises(vsm, fake_collection):
    fake_collection.has_partition.return_value = False
    with patch("app.services.vector_store_manager.vector_embedding_service") as emb:
        from app.services.vector_store_manager import KBNotFoundError
        with pytest.raises(KBNotFoundError):
            vsm.similarity_search_in_partition("query", "xhs_missing", k=3)
```

- [ ] **Step 3.2: 跑测试确认失败**

Run: `pytest tests/services/test_vector_store_manager_partition.py -v`
Expected: 后 4 个 fail（方法/异常类未定义）

- [ ] **Step 3.3: 实现 add/search 方法 + KBNotFoundError**

在 `app/services/vector_store_manager.py` 顶部 import 区追加：

```python
import uuid
```

在文件顶部（class 外）追加自定义异常：

```python
class KBNotFoundError(Exception):
    """请求的知识库（partition）不存在。"""
```

在 `VectorStoreManager` 类内（接在 Task 2 三个方法之后）追加：

```python
    def add_documents_to_partition(
        self, documents: List[Document], kb_name: str,
    ) -> List[str]:
        """入库到指定 partition。返回生成的 id 列表。"""
        if not documents:
            return []

        collection = milvus_manager.get_collection()
        if not collection.has_partition(kb_name):
            collection.create_partition(partition_name=kb_name)

        from app.services.vector_embedding_service import vector_embedding_service

        texts = [d.page_content for d in documents]
        metadatas = [d.metadata or {} for d in documents]
        vectors = vector_embedding_service.embed_documents(texts)
        ids = [str(uuid.uuid4()) for _ in documents]

        # 列式插入：与 milvus_client._create_collection 中的字段顺序一致
        # [id (VARCHAR), vector (FLOAT_VECTOR), content (VARCHAR), metadata (JSON)]
        collection.insert(
            data=[ids, vectors, texts, metadatas],
            partition_name=kb_name,
        )
        collection.flush()
        logger.info(f"partition '{kb_name}' 入库 {len(ids)} 向量")
        return ids

    def similarity_search_in_partition(
        self, query: str, kb_name: str, k: int = 3,
    ) -> List[Document]:
        """仅在指定 partition 内向量检索。"""
        collection = milvus_manager.get_collection()
        if not collection.has_partition(kb_name):
            raise KBNotFoundError(f"知识库 '{kb_name}' 不存在")

        # 新建 partition 默认未加载到内存，需主动 load（已加载时是 no-op）
        try:
            collection.partition(kb_name).load()
        except Exception as e:
            logger.debug(f"partition '{kb_name}' load: {e}")

        from app.services.vector_embedding_service import vector_embedding_service

        qv = vector_embedding_service.embed_query(query)
        results = collection.search(
            data=[qv],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 16}},
            limit=k,
            partition_names=[kb_name],
            output_fields=["content", "metadata"],
        )
        docs: List[Document] = []
        for hit in results[0]:
            docs.append(Document(
                page_content=hit.entity.get("content") or "",
                metadata=hit.entity.get("metadata") or {},
            ))
        logger.debug(f"partition '{kb_name}' 检索 query='{query[:30]}' 命中 {len(docs)}")
        return docs
```

- [ ] **Step 3.4: 跑测试确认通过**

Run: `pytest tests/services/test_vector_store_manager_partition.py -v`
Expected: 9 passed（Task 2 的 5 个 + Task 3 的 4 个）

- [ ] **Step 3.5: Commit**

```bash
git add app/services/vector_store_manager.py tests/services/test_vector_store_manager_partition.py
git commit -m "feat(vector-store): add partition-scoped insert and similarity search"
```

---

## Task 4: xhs_ingestion_service 自动生成 kb_name 并走 partition

**Files:**
- Modify: `app/services/xhs_ingestion_service.py`
- Create: `tests/services/test_xhs_ingestion_service.py`

- [ ] **Step 4.1: 写失败测试**

`tests/services/test_xhs_ingestion_service.py`：

```python
"""tests for xhs_ingestion_service"""

import re
from unittest.mock import patch, MagicMock

import pytest

from app.services import xhs_ingestion_service as svc


def test_make_kb_name_format():
    name = svc._make_kb_name("美食攻略", "成都")
    # xhs_<8位hex>_<YYYYMMDD>_<HHMMSS>
    assert re.match(r"^xhs_[0-9a-f]{8}_\d{8}_\d{6}$", name)


def test_make_kb_name_empty_city_still_valid():
    name = svc._make_kb_name("关键词", "")
    assert re.match(r"^xhs_[0-9a-f]{8}_\d{8}_\d{6}$", name)


def test_make_kb_name_deterministic_per_input_modulo_time():
    """同 keyword+city 的 hex 短哈希应一致（时间戳除外）。"""
    n1 = svc._make_kb_name("k", "c")
    n2 = svc._make_kb_name("k", "c")
    # 取 xhs_<hex>_ 之前的部分
    assert n1.split("_")[1] == n2.split("_")[1]


def test_ingest_notes_creates_partition_and_inserts():
    notes = [{
        "note_id": "n1", "title": "T", "content": "C" * 50,
        "city": "成都", "tags": ["美食"], "author": "a", "url": "u", "likes": 9,
    }]
    with patch("app.services.xhs_ingestion_service.vector_store_manager") as vsm:
        vsm.add_documents_to_partition.return_value = ["id-1"]
        result = svc.ingest_notes(notes, kb_name="xhs_test_20260514_120000",
                                  description="t|c")
    assert result == {"ingested": 1, "chunks": 1}
    vsm.ensure_partition.assert_called_once_with(
        "xhs_test_20260514_120000", description="t|c"
    )
    vsm.add_documents_to_partition.assert_called_once()
    docs_arg, kb_arg = vsm.add_documents_to_partition.call_args.args[:2] if vsm.add_documents_to_partition.call_args.args else (
        vsm.add_documents_to_partition.call_args.kwargs.get("documents"),
        vsm.add_documents_to_partition.call_args.kwargs.get("kb_name"),
    )


def test_ingest_notes_empty_does_not_create_partition():
    with patch("app.services.xhs_ingestion_service.vector_store_manager") as vsm:
        result = svc.ingest_notes([], kb_name="xhs_x_20260514_120000",
                                  description="")
    assert result == {"ingested": 0, "chunks": 0}
    vsm.ensure_partition.assert_not_called()
    vsm.add_documents_to_partition.assert_not_called()


@pytest.mark.asyncio
async def test_ingest_from_mcp_returns_kb_name():
    fake_notes = [{
        "note_id": "n1", "title": "T", "content": "X" * 100,
        "city": "成都", "tags": [], "author": "", "url": "", "likes": 0,
    }]
    with patch("app.services.xhs_ingestion_service._fetch_notes_from_mcp",
               new=MagicMock(return_value=fake_notes)) as fetch, \
         patch("app.services.xhs_ingestion_service.vector_store_manager") as vsm:
        # _fetch_notes_from_mcp 是 async 函数，需用 AsyncMock
        from unittest.mock import AsyncMock
        fetch_async = AsyncMock(return_value=fake_notes)
        with patch("app.services.xhs_ingestion_service._fetch_notes_from_mcp",
                   new=fetch_async):
            vsm.add_documents_to_partition.return_value = ["id-1"]
            result = await svc.ingest_from_mcp("k", "成都", count=3)

    assert result["kb_name"] is not None
    assert result["kb_name"].startswith("xhs_")
    assert result["ingested"] == 1


@pytest.mark.asyncio
async def test_ingest_from_mcp_zero_notes_returns_null_kb_name():
    from unittest.mock import AsyncMock
    fetch_async = AsyncMock(return_value=[])
    with patch("app.services.xhs_ingestion_service._fetch_notes_from_mcp",
               new=fetch_async), \
         patch("app.services.xhs_ingestion_service.vector_store_manager") as vsm:
        result = await svc.ingest_from_mcp("k", "c", count=3)
    assert result["kb_name"] is None
    assert result["ingested"] == 0
    vsm.ensure_partition.assert_not_called()
```

- [ ] **Step 4.2: 跑测试确认失败**

Run: `pytest tests/services/test_xhs_ingestion_service.py -v`
Expected: 多数 fail（`_make_kb_name` 不存在；`ingest_notes` 签名不接受 `kb_name`）

- [ ] **Step 4.3: 重写 xhs_ingestion_service**

整体替换 `app/services/xhs_ingestion_service.py`：

```python
"""小红书笔记入库管道：MCP 搜索 → 分块 → 向量化 → Milvus partition"""

import hashlib
from datetime import datetime
from typing import Any, Dict, List, Optional

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from app.config import config
from app.services.vector_store_manager import vector_store_manager


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.chunk_max_size,
    chunk_overlap=config.chunk_overlap,
)


def _make_kb_name(keyword: str, city: str) -> str:
    """生成 partition 名：xhs_<md5前8位>_<YYYYMMDD>_<HHMMSS>"""
    seed = f"{keyword}|{city}".encode("utf-8")
    short = hashlib.md5(seed).hexdigest()[:8]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"xhs_{short}_{ts}"


def _note_to_docs(note: dict) -> List[Document]:
    """将一条 XHS 笔记拆分为 LangChain Document 列表"""
    full_text = f"【{note.get('title', '')}】\n{note.get('content', '')}"
    chunks = _splitter.split_text(full_text)
    docs = []
    for i, chunk in enumerate(chunks):
        docs.append(Document(
            page_content=chunk,
            metadata={
                "_source": note.get("url", "xhs"),
                "_file_name": note.get("title", "xhs_note"),
                "note_id": note.get("note_id", ""),
                "city": note.get("city", ""),
                "tags": ",".join(note.get("tags", [])),
                "author": note.get("author", ""),
                "likes": note.get("likes", 0),
                "chunk_index": i,
                "source_type": "xhs",
            },
        ))
    return docs


async def _fetch_notes_from_mcp(keyword: str, city: str, count: int) -> List[dict]:
    """通过 XHS MCP 搜索笔记"""
    from fastmcp import Client

    async with Client(config.mcp_xhs_url) as client:
        result = await client.call_tool(
            "xhs_search_notes",
            {"keyword": keyword, "city": city, "count": count},
        )
    import json
    raw = result[0].text if result else "{}"
    data = json.loads(raw)
    return data.get("notes", [])


def ingest_notes(
    notes: List[dict],
    kb_name: str,
    description: str = "",
) -> Dict[str, Any]:
    """将笔记列表入库到指定 partition，返回入库统计。"""
    if not notes:
        return {"ingested": 0, "chunks": 0}

    all_docs: List[Document] = []
    for note in notes:
        all_docs.extend(_note_to_docs(note))
    if not all_docs:
        return {"ingested": 0, "chunks": 0}

    vector_store_manager.ensure_partition(kb_name, description=description)
    ids = vector_store_manager.add_documents_to_partition(all_docs, kb_name)
    logger.info(f"XHS 入库完成 partition='{kb_name}': {len(notes)} 笔记 → {len(ids)} 块")
    return {"ingested": len(notes), "chunks": len(ids)}


async def ingest_from_mcp(
    keyword: str, city: str = "", count: int = 10,
) -> Dict[str, Any]:
    """从 XHS MCP 搜索并入库。0 笔记时不创建 partition，kb_name 返 None。"""
    logger.info(f"XHS MCP 搜索入库: keyword={keyword}, city={city}, count={count}")
    notes = await _fetch_notes_from_mcp(keyword, city, count)
    if not notes:
        return {"kb_name": None, "ingested": 0, "chunks": 0,
                "keyword": keyword, "city": city}

    kb_name = _make_kb_name(keyword, city)
    description = f"{keyword}|{city}"
    result = ingest_notes(notes, kb_name=kb_name, description=description)
    return {"kb_name": kb_name, **result, "keyword": keyword, "city": city}


def ingest_raw_text(
    title: str, content: str, city: str = "", tags: Optional[list] = None,
    kb_name: Optional[str] = None,
) -> Dict[str, Any]:
    """直接入库手动粘贴的 XHS 内容。kb_name 不传时默认 xhs_manual_<ts>。"""
    note = {
        "note_id": hashlib.md5(content.encode()).hexdigest()[:12],
        "title": title,
        "content": content,
        "city": city,
        "tags": tags or [],
        "author": "manual",
        "url": "manual",
        "likes": 0,
    }
    if not kb_name:
        kb_name = f"xhs_manual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    description = f"manual|{city}"
    result = ingest_notes([note], kb_name=kb_name, description=description)
    return {"kb_name": kb_name, **result}
```

- [ ] **Step 4.4: 跑测试确认通过**

Run: `pytest tests/services/test_xhs_ingestion_service.py -v`
Expected: 7 passed

- [ ] **Step 4.5: Commit**

```bash
git add app/services/xhs_ingestion_service.py tests/services/test_xhs_ingestion_service.py
git commit -m "feat(xhs): generate kb_name per ingest and route notes into Milvus partition"
```

---

## Task 5: xhs API 增加 list / delete 端点 + ingest 校验

**Files:**
- Modify: `app/api/xhs.py`
- Create: `tests/api/test_xhs_api.py`

- [ ] **Step 5.1: 写失败测试**

`tests/api/test_xhs_api.py`：

```python
"""tests for /api/xhs/* endpoints"""

import re
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """构造一个挂载了 xhs 路由的最小 app（避免初始化全部依赖）。"""
    from fastapi import FastAPI
    from app.api import xhs
    app = FastAPI()
    app.include_router(xhs.router, prefix="/api")
    return TestClient(app)


def test_ingest_mcp_returns_kb_name(client):
    with patch("app.api.xhs.ingest_from_mcp",
               new=AsyncMock(return_value={
                   "kb_name": "xhs_abc_20260514_120000",
                   "ingested": 3, "chunks": 12,
                   "keyword": "k", "city": "c",
               })):
        resp = client.post("/api/xhs/ingest/mcp",
                           json={"keyword": "k", "city": "c", "count": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["kb_name"] == "xhs_abc_20260514_120000"
    assert body["data"]["chunks"] == 12


def test_ingest_text_with_invalid_kb_name_returns_400(client):
    resp = client.post("/api/xhs/ingest/text",
                       json={"title": "t", "content": "c",
                             "kb_name": "中文不合法"})
    assert resp.status_code == 200  # FastAPI 仍返 200，我们用 code 字段表错误
    assert resp.json()["code"] == 400


def test_ingest_text_with_default_kb_name(client):
    with patch("app.api.xhs.ingest_raw_text",
               return_value={"kb_name": "xhs_manual_20260514_120000",
                             "ingested": 1, "chunks": 1}):
        resp = client.post("/api/xhs/ingest/text",
                           json={"title": "t", "content": "c"})
    assert resp.json()["code"] == 200
    assert resp.json()["data"]["kb_name"].startswith("xhs_manual_")


def test_kb_list(client):
    with patch("app.api.xhs.vector_store_manager") as vsm:
        vsm.list_kb_partitions.return_value = [
            {"kb_name": "xhs_abc_20260514_120000",
             "num_entities": 47, "description": "美食|成都"},
        ]
        resp = client.get("/api/xhs/kb/list")
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["total"] == 1
    assert body["data"]["kbs"][0]["kb_name"] == "xhs_abc_20260514_120000"
    assert body["data"]["kbs"][0]["created_at"] == "2026-05-14 12:00:00"


def test_kb_delete_success(client):
    with patch("app.api.xhs.vector_store_manager") as vsm:
        vsm.drop_kb_partition.return_value = 47
        resp = client.delete("/api/xhs/kb/xhs_abc_20260514_120000")
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["deleted_entities"] == 47


def test_kb_delete_not_found(client):
    with patch("app.api.xhs.vector_store_manager") as vsm:
        vsm.drop_kb_partition.return_value = -1
        resp = client.delete("/api/xhs/kb/xhs_missing_00000000_000000")
    body = resp.json()
    assert body["code"] == 404
```

- [ ] **Step 5.2: 跑测试确认失败**

Run: `pytest tests/api/test_xhs_api.py -v`
Expected: 多数 fail（路由 / 行为缺失）

- [ ] **Step 5.3: 重写 xhs.py**

整体替换 `app/api/xhs.py`：

```python
"""小红书 RAG 管理接口"""

import re
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.xhs_ingestion_service import ingest_from_mcp, ingest_raw_text
from app.services.vector_store_manager import vector_store_manager
from app.core.milvus_client import milvus_manager

router = APIRouter()

# Milvus partition 名约束：字母数字下划线，最长 255
_KB_NAME_RE = re.compile(r"^xhs_[a-zA-Z0-9_]{1,240}$")


class RawIngestRequest(BaseModel):
    title: str
    content: str
    city: str = ""
    tags: List[str] = []
    kb_name: Optional[str] = None


class McpIngestRequest(BaseModel):
    keyword: str = "旅游攻略"
    city: str = ""
    count: int = 10


def _parse_created_at(kb_name: str) -> str:
    """从 xhs_<hex>_YYYYMMDD_HHMMSS 末尾解析时间，失败返空串。"""
    parts = kb_name.split("_")
    if len(parts) < 4:
        return ""
    date, time_ = parts[-2], parts[-1]
    if len(date) == 8 and len(time_) == 6 and date.isdigit() and time_.isdigit():
        return f"{date[:4]}-{date[4:6]}-{date[6:8]} {time_[:2]}:{time_[2:4]}:{time_[4:6]}"
    return ""


@router.post("/xhs/ingest/text")
async def ingest_text(body: RawIngestRequest):
    """手动粘贴小红书内容入库（无需 MCP）"""
    if body.kb_name and not _KB_NAME_RE.match(body.kb_name):
        return {"code": 400,
                "message": "kb_name 必须满足 ^xhs_[a-zA-Z0-9_]{1,240}$",
                "data": None}
    result = ingest_raw_text(
        title=body.title,
        content=body.content,
        city=body.city,
        tags=body.tags,
        kb_name=body.kb_name,
    )
    return {"code": 200, "message": "入库成功", "data": result}


@router.post("/xhs/ingest/mcp")
async def ingest_mcp(body: McpIngestRequest):
    """通过 XHS MCP 搜索并批量入库（需启动 xhs_server.py）"""
    try:
        result = await ingest_from_mcp(
            keyword=body.keyword,
            city=body.city,
            count=body.count,
        )
        return {"code": 200, "message": "入库成功", "data": result}
    except Exception as e:
        return {"code": 500, "message": f"MCP 连接失败: {e}", "data": None}


@router.get("/xhs/kb/list")
async def kb_list():
    """列出所有 xhs_ 开头的知识库分区。"""
    try:
        kbs = vector_store_manager.list_kb_partitions()
        for kb in kbs:
            kb["created_at"] = _parse_created_at(kb["kb_name"])
        return {"code": 200, "data": {"total": len(kbs), "kbs": kbs}}
    except Exception as e:
        return {"code": 500, "message": str(e), "data": None}


@router.delete("/xhs/kb/{kb_name}")
async def kb_delete(kb_name: str):
    """删除指定知识库分区。"""
    if not _KB_NAME_RE.match(kb_name):
        return {"code": 400, "message": "kb_name 格式非法", "data": None}
    try:
        n = vector_store_manager.drop_kb_partition(kb_name)
        if n == -1:
            return {"code": 404,
                    "message": f"知识库 '{kb_name}' 不存在", "data": None}
        return {"code": 200, "data": {"kb_name": kb_name, "deleted_entities": n}}
    except Exception as e:
        return {"code": 500, "message": str(e), "data": None}


@router.get("/xhs/stats")
async def xhs_stats():
    """查看 Milvus 中的 XHS 数据统计"""
    try:
        collection = milvus_manager.get_collection()
        total = collection.num_entities
        return {
            "code": 200,
            "data": {
                "total_vectors": total,
                "collection": "biz",
                "note": "所有来源（XHS + 其他文档）共用 biz collection",
            },
        }
    except Exception as e:
        return {"code": 500, "message": str(e), "data": None}
```

- [ ] **Step 5.4: 跑测试确认通过**

Run: `pytest tests/api/test_xhs_api.py -v`
Expected: 6 passed

- [ ] **Step 5.5: Commit**

```bash
git add app/api/xhs.py tests/api/test_xhs_api.py
git commit -m "feat(xhs-api): add kb list/delete endpoints; return kb_name on ingest; validate kb_name"
```

---

## Task 6: rag_service 检索 + prompt + citations

**Files:**
- Create: `app/services/rag_service.py`
- Create: `tests/services/test_rag_service.py`

- [ ] **Step 6.1: 写失败测试**

`tests/services/test_rag_service.py`：

```python
"""tests for rag_service.build_rag_context"""

from unittest.mock import patch
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage


def _doc(content, **meta):
    return Document(page_content=content, metadata=meta)


def test_build_rag_context_hits_nonempty():
    from app.services import rag_service
    docs = [
        _doc("成都必吃郫县豆瓣鱼",
             _file_name="成都美食攻略", _source="https://x/1",
             author="A", likes=100, note_id="n1"),
        _doc("夫妻肺片麻辣过瘾",
             _file_name="成都美食攻略", _source="https://x/1",
             author="A", likes=100, note_id="n1"),   # 同 note_id 去重
        _doc("钟水饺甜辣口",
             _file_name="小吃推荐", _source="https://x/2",
             author="B", likes=50, note_id="n2"),
    ]
    with patch("app.services.rag_service.vector_store_manager") as vsm:
        vsm.similarity_search_in_partition.return_value = docs
        ctx = rag_service.build_rag_context(
            "成都美食推荐", history=[], kb_name="xhs_a_20260514_120000", top_k=3,
        )

    assert ctx.hit_count == 3
    assert len(ctx.citations) == 2  # note_id 去重后
    assert ctx.citations[0].title == "成都美食攻略"
    assert ctx.citations[1].title == "小吃推荐"

    # 系统消息含参考资料
    sys_msg = ctx.messages[0]
    assert isinstance(sys_msg, SystemMessage)
    assert "参考资料" in sys_msg.content
    assert "郫县豆瓣鱼" in sys_msg.content

    # 末尾是用户问题
    assert isinstance(ctx.messages[-1], HumanMessage)
    assert ctx.messages[-1].content == "成都美食推荐"


def test_build_rag_context_empty_hits_fallback():
    from app.services import rag_service
    with patch("app.services.rag_service.vector_store_manager") as vsm:
        vsm.similarity_search_in_partition.return_value = []
        ctx = rag_service.build_rag_context(
            "成都天气", history=[], kb_name="xhs_a_20260514_120000", top_k=3,
        )
    assert ctx.hit_count == 0
    assert ctx.citations == []
    sys_msg = ctx.messages[0]
    assert "未检索到" in sys_msg.content or "通用建议" in sys_msg.content


def test_build_rag_context_history_truncated_to_20():
    from app.services import rag_service
    history = [{"role": "user" if i % 2 == 0 else "assistant",
                "content": f"msg-{i}"} for i in range(30)]
    with patch("app.services.rag_service.vector_store_manager") as vsm:
        vsm.similarity_search_in_partition.return_value = []
        ctx = rag_service.build_rag_context(
            "q", history=history, kb_name="xhs_a_20260514_120000", top_k=3,
        )
    # 1 system + 20 history + 1 human
    assert len(ctx.messages) == 22


def test_build_rag_context_propagates_kb_not_found():
    from app.services import rag_service
    from app.services.vector_store_manager import KBNotFoundError
    with patch("app.services.rag_service.vector_store_manager") as vsm:
        vsm.similarity_search_in_partition.side_effect = KBNotFoundError("nope")
        import pytest
        with pytest.raises(KBNotFoundError):
            rag_service.build_rag_context("q", history=[],
                                          kb_name="xhs_missing", top_k=3)
```

- [ ] **Step 6.2: 跑测试确认失败**

Run: `pytest tests/services/test_rag_service.py -v`
Expected: ImportError（rag_service 不存在）

- [ ] **Step 6.3: 实现 rag_service**

`app/services/rag_service.py`：

```python
"""RAG 上下文构造：检索 + prompt 拼接 + citations 去重。"""

from dataclasses import dataclass
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from app.services.vector_store_manager import vector_store_manager


@dataclass
class Citation:
    title: str
    url: str
    author: str
    likes: int


@dataclass
class RagContext:
    messages: List[BaseMessage]
    citations: List[Citation]
    hit_count: int


_SYSTEM_PROMPT_WITH_CONTEXT = """你是一个智能旅游助手。请基于下面的小红书攻略参考资料回答用户问题。
- 优先使用参考资料中的信息
- 如果参考资料不足，可以基于通用常识补充，但要明确标注"以下为通用建议"
- 不要编造资料里没有的具体地名/价格/路线

【参考资料】
{context_block}
"""

_SYSTEM_PROMPT_NO_HIT = """你是一个智能旅游助手。指定知识库中未检索到与本问题相关的内容，请基于通用常识简洁回答用户问题，并在开头注明"以下为通用建议"。"""


def _format_context(docs: List[Document]) -> str:
    blocks = []
    for i, d in enumerate(docs, 1):
        md = d.metadata or {}
        title = md.get("_file_name", "")
        author = md.get("author", "")
        likes = md.get("likes", 0)
        blocks.append(
            f"[{i}] 标题：{title}（作者：{author}，{likes} 赞）\n    内容：{d.page_content}"
        )
    return "\n".join(blocks)


def _extract_citations(docs: List[Document]) -> List[Citation]:
    seen = set()
    out: List[Citation] = []
    for d in docs:
        md = d.metadata or {}
        nid = md.get("note_id", "")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(Citation(
            title=md.get("_file_name", ""),
            url=md.get("_source", ""),
            author=md.get("author", ""),
            likes=md.get("likes", 0),
        ))
    return out


def _history_to_lc(history: List[dict]) -> List[BaseMessage]:
    msgs: List[BaseMessage] = []
    for h in history[-20:]:
        if h["role"] == "user":
            msgs.append(HumanMessage(content=h["content"]))
        else:
            msgs.append(AIMessage(content=h["content"]))
    return msgs


def build_rag_context(
    question: str,
    history: List[dict],
    kb_name: str,
    top_k: int = 3,
) -> RagContext:
    """检索 kb_name → 构造 messages + citations。

    KB 不存在时抛 KBNotFoundError（来自 vector_store_manager）。
    """
    docs = vector_store_manager.similarity_search_in_partition(
        query=question, kb_name=kb_name, k=top_k,
    )
    logger.info(f"RAG kb='{kb_name}' query='{question[:30]}' hits={len(docs)}")

    if docs:
        sys_content = _SYSTEM_PROMPT_WITH_CONTEXT.format(
            context_block=_format_context(docs)
        )
    else:
        sys_content = _SYSTEM_PROMPT_NO_HIT

    messages: List[BaseMessage] = [SystemMessage(content=sys_content)]
    messages.extend(_history_to_lc(history))
    messages.append(HumanMessage(content=question))

    return RagContext(
        messages=messages,
        citations=_extract_citations(docs),
        hit_count=len(docs),
    )
```

- [ ] **Step 6.4: 跑测试确认通过**

Run: `pytest tests/services/test_rag_service.py -v`
Expected: 4 passed

- [ ] **Step 6.5: Commit**

```bash
git add app/services/rag_service.py tests/services/test_rag_service.py
git commit -m "feat(rag): add rag_service to build RAG context with citations dedup"
```

---

## Task 7: /api/chat/rag 阻塞端点

**Files:**
- Create: `app/api/chat_rag.py`
- Create: `tests/api/test_chat_rag_api.py`

- [ ] **Step 7.1: 写失败测试**

`tests/api/test_chat_rag_api.py`：

```python
"""tests for /api/chat/rag and /api/chat/rag_stream"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage


@pytest.fixture
def client():
    from fastapi import FastAPI
    from app.api import chat_rag
    app = FastAPI()
    app.include_router(chat_rag.router, prefix="/api")
    return TestClient(app)


def _ctx_with_hits():
    from app.services.rag_service import RagContext, Citation
    return RagContext(
        messages=[],
        citations=[Citation(title="T", url="u", author="a", likes=9)],
        hit_count=1,
    )


def test_chat_rag_missing_kb_name_returns_400(client):
    resp = client.post("/api/chat/rag",
                       json={"Question": "q", "session_id": "s1"})
    body = resp.json()
    assert body["code"] == 400
    assert "kb_name" in body["message"]


def test_chat_rag_happy_path(client):
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="答案"))
    with patch("app.api.chat_rag.build_rag_context", return_value=_ctx_with_hits()), \
         patch("app.api.chat_rag.LLMFactory.create_travel_llm", return_value=fake_llm), \
         patch("app.api.chat_rag.session_store") as ss:
        ss.get.return_value = []
        resp = client.post("/api/chat/rag",
                           json={"Question": "成都美食",
                                 "session_id": "s1",
                                 "kb_name": "xhs_a_20260514_120000"})
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["answer"] == "答案"
    assert body["data"]["citations"][0]["title"] == "T"
    assert body["data"]["hit_count"] == 1


def test_chat_rag_kb_not_found_returns_404(client):
    from app.services.vector_store_manager import KBNotFoundError
    with patch("app.api.chat_rag.build_rag_context",
               side_effect=KBNotFoundError("nope")):
        resp = client.post("/api/chat/rag",
                           json={"Question": "q",
                                 "session_id": "s1",
                                 "kb_name": "xhs_missing"})
    assert resp.json()["code"] == 404
```

- [ ] **Step 7.2: 跑测试确认失败**

Run: `pytest tests/api/test_chat_rag_api.py -v`
Expected: ImportError（chat_rag 不存在）

- [ ] **Step 7.3: 实现 chat_rag.py 的阻塞端点**

创建 `app/api/chat_rag.py`：

```python
"""RAG 对话 API — /chat/rag 阻塞 + /chat/rag_stream SSE"""

import json
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from app.config import config
from app.core.llm_factory import LLMFactory
from app.services import session_store
from app.services.rag_service import build_rag_context
from app.services.vector_store_manager import KBNotFoundError

router = APIRouter()


class RagChatRequest(BaseModel):
    Question: str = ""
    session_id: Optional[str] = "default"
    kb_name: str = ""
    top_k: Optional[int] = None


def _sid(req: RagChatRequest) -> str:
    return req.session_id or "default"


def _validate(req: RagChatRequest):
    if not req.Question.strip():
        return {"code": 400, "message": "Question 不能为空", "data": None}
    if not req.kb_name.strip():
        return {"code": 400, "message": "kb_name 必填", "data": None}
    return None


@router.post("/chat/rag")
async def chat_rag(request: RagChatRequest):
    err = _validate(request)
    if err:
        return err

    sid = _sid(request)
    history = session_store.get(sid)
    top_k = request.top_k or config.rag_top_k

    try:
        ctx = build_rag_context(
            question=request.Question,
            history=history,
            kb_name=request.kb_name,
            top_k=top_k,
        )
    except KBNotFoundError as e:
        return {"code": 404, "message": str(e), "data": None}
    except Exception as e:
        logger.exception("build_rag_context error: {}", repr(e))
        return {"code": 500, "message": str(e), "data": None}

    try:
        llm = LLMFactory.create_travel_llm(temperature=0.7, streaming=False)
        resp = await llm.ainvoke(ctx.messages)
        answer = resp.content
    except Exception as e:
        logger.exception("llm error: {}", repr(e))
        return {"code": 500, "message": str(e),
                "data": {"success": False, "answer": None,
                         "errorMessage": str(e)}}

    session_store.append(sid, "user", request.Question)
    session_store.append(sid, "assistant", answer)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "success": True,
            "answer": answer,
            "citations": [asdict(c) for c in ctx.citations],
            "hit_count": ctx.hit_count,
            "errorMessage": None,
        },
    }
```

- [ ] **Step 7.4: 跑测试确认通过**

Run: `pytest tests/api/test_chat_rag_api.py -v`
Expected: 3 passed

- [ ] **Step 7.5: Commit**

```bash
git add app/api/chat_rag.py tests/api/test_chat_rag_api.py
git commit -m "feat(chat-rag): add /api/chat/rag blocking endpoint with citations"
```

---

## Task 8: /api/chat/rag_stream SSE 流式端点

**Files:**
- Modify: `app/api/chat_rag.py`
- Modify: `tests/api/test_chat_rag_api.py`

- [ ] **Step 8.1: 追加失败测试**

在 `tests/api/test_chat_rag_api.py` 末尾追加：

```python
def _async_chunk_iter(chunks):
    """构造一个 async iterator，仿 LLM astream 输出。"""
    async def _gen():
        for c in chunks:
            chunk = MagicMock()
            chunk.content = c
            yield chunk
    return _gen()


def test_chat_rag_stream_emits_citations_then_content_then_done(client):
    fake_llm = MagicMock()
    fake_llm.astream = MagicMock(return_value=_async_chunk_iter(["答", "案"]))

    with patch("app.api.chat_rag.build_rag_context", return_value=_ctx_with_hits()), \
         patch("app.api.chat_rag.LLMFactory.create_travel_llm", return_value=fake_llm), \
         patch("app.api.chat_rag.session_store") as ss:
        ss.get.return_value = []
        with client.stream("POST", "/api/chat/rag_stream",
                           json={"Question": "q",
                                 "session_id": "s1",
                                 "kb_name": "xhs_a_20260514_120000"}) as resp:
            assert resp.status_code == 200
            events = []
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))

    assert events[0]["type"] == "citations"
    assert events[0]["data"][0]["title"] == "T"
    types = [e["type"] for e in events]
    assert "content" in types
    assert events[-1]["type"] == "done"


def test_chat_rag_stream_kb_not_found_emits_error(client):
    from app.services.vector_store_manager import KBNotFoundError
    with patch("app.api.chat_rag.build_rag_context",
               side_effect=KBNotFoundError("nope")):
        with client.stream("POST", "/api/chat/rag_stream",
                           json={"Question": "q",
                                 "session_id": "s1",
                                 "kb_name": "xhs_missing"}) as resp:
            events = []
            for line in resp.iter_lines():
                if line.startswith("data: "):
                    events.append(json.loads(line[6:]))
    assert any(e["type"] == "error" for e in events)
```

- [ ] **Step 8.2: 跑测试确认失败**

Run: `pytest tests/api/test_chat_rag_api.py -v`
Expected: 后 2 个 fail（路由 `/chat/rag_stream` 未注册）

- [ ] **Step 8.3: 在 chat_rag.py 追加 SSE 端点**

在 `app/api/chat_rag.py` 末尾追加：

```python
@router.post("/chat/rag_stream")
async def chat_rag_stream(request: RagChatRequest):
    err = _validate(request)
    sid = _sid(request)

    async def generate():
        if err:
            yield f"data: {json.dumps({'type':'error','data':err['message']}, ensure_ascii=False)}\n\n"
            return

        history = session_store.get(sid)
        top_k = request.top_k or config.rag_top_k

        try:
            ctx = build_rag_context(
                question=request.Question,
                history=history,
                kb_name=request.kb_name,
                top_k=top_k,
            )
        except KBNotFoundError as e:
            yield f"data: {json.dumps({'type':'error','data':str(e)}, ensure_ascii=False)}\n\n"
            return
        except Exception as e:
            logger.exception("build_rag_context error: {}", repr(e))
            yield f"data: {json.dumps({'type':'error','data':str(e)}, ensure_ascii=False)}\n\n"
            return

        citations_payload = [asdict(c) for c in ctx.citations]
        yield f"data: {json.dumps({'type':'citations','data':citations_payload}, ensure_ascii=False)}\n\n"

        full = ""
        try:
            llm = LLMFactory.create_travel_llm(temperature=0.7, streaming=True)
            async for chunk in llm.astream(ctx.messages):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    full += content
                    yield f"data: {json.dumps({'type':'content','data':content}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("llm stream error: {}", repr(e))
            yield f"data: {json.dumps({'type':'error','data':str(e)}, ensure_ascii=False)}\n\n"
            return

        session_store.append(sid, "user", request.Question)
        session_store.append(sid, "assistant", full)
        yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

- [ ] **Step 8.4: 跑测试确认通过**

Run: `pytest tests/api/test_chat_rag_api.py -v`
Expected: 5 passed

- [ ] **Step 8.5: Commit**

```bash
git add app/api/chat_rag.py tests/api/test_chat_rag_api.py
git commit -m "feat(chat-rag): add /api/chat/rag_stream SSE endpoint"
```

---

## Task 9: 在 main.py 注册新路由

**Files:**
- Modify: `app/main.py`

- [ ] **Step 9.1: 修改 main.py**

把 `app/main.py` 第 12 行：

```python
from app.api import health, travel, chat
```

替换为：

```python
from app.api import health, travel, chat, xhs, chat_rag
```

把 `app/main.py` 第 44-46 行的 router 注册区改为：

```python
app.include_router(health.router, tags=["健康检查"])
app.include_router(travel.router, prefix="/api", tags=["旅游规划"])
app.include_router(chat.router, prefix="/api", tags=["聊天"])
app.include_router(chat_rag.router, prefix="/api", tags=["RAG 对话"])
app.include_router(xhs.router, prefix="/api", tags=["小红书 RAG"])
```

- [ ] **Step 9.2: 启动服务做冒烟测试**

Run: `python -m uvicorn app.main:app --port 9900`

在另一个 shell（或浏览器）访问 http://localhost:9900/docs，确认看到：
- `/api/chat/rag`、`/api/chat/rag_stream` 标签 "RAG 对话"
- `/api/xhs/ingest/mcp`、`/api/xhs/ingest/text`、`/api/xhs/kb/list`、`/api/xhs/kb/{kb_name}` (DELETE)、`/api/xhs/stats` 标签 "小红书 RAG"

Ctrl-C 停止 uvicorn。

- [ ] **Step 9.3: 跑全量测试**

Run: `pytest tests/ -v`
Expected: 全部 passed（包括新增的 ~25 个测试 + 原有测试无回归）

- [ ] **Step 9.4: Commit**

```bash
git add app/main.py
git commit -m "feat(main): register xhs and chat_rag routers"
```

---

## Task 10: 集成测试（连真 Milvus，可选跳过）

**Files:**
- Create: `tests/services/test_vector_store_partition_integration.py`

- [ ] **Step 10.1: 写集成测试**

`tests/services/test_vector_store_partition_integration.py`：

```python
"""集成测试：连真 Milvus 验证 partition 增删查的端到端行为。

需 Milvus 本地运行；设置环境变量 RUN_MILVUS_TESTS=1 才执行。
测试结束后会清理自身创建的 partition。
"""

import os
import uuid

import pytest
from langchain_core.documents import Document

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_MILVUS_TESTS") != "1",
    reason="集成测试，需 Milvus 运行并设置 RUN_MILVUS_TESTS=1",
)


@pytest.fixture
def kb_name():
    # 使用 uuid 后缀避免与他人测试碰撞
    name = f"xhs_itest_{uuid.uuid4().hex[:8]}_20260514_120000"
    yield name
    # teardown
    try:
        from app.services.vector_store_manager import vector_store_manager
        vector_store_manager.drop_kb_partition(name)
    except Exception:
        pass


def test_ensure_then_insert_then_search(kb_name):
    from app.services.vector_store_manager import vector_store_manager

    vector_store_manager.ensure_partition(kb_name, description="itest")
    docs = [
        Document(page_content="成都必吃郫县豆瓣鱼夫妻肺片",
                 metadata={"note_id": "n1", "_file_name": "成都美食",
                           "author": "A", "likes": 1, "_source": "u1"}),
        Document(page_content="北京烤鸭推荐大董四季民福",
                 metadata={"note_id": "n2", "_file_name": "北京烤鸭",
                           "author": "B", "likes": 2, "_source": "u2"}),
    ]
    ids = vector_store_manager.add_documents_to_partition(docs, kb_name)
    assert len(ids) == 2

    hits = vector_store_manager.similarity_search_in_partition(
        "成都美食推荐", kb_name, k=2,
    )
    assert len(hits) >= 1
    # 第一名应是成都那条
    assert "成都" in hits[0].page_content or "豆瓣" in hits[0].page_content


def test_partition_isolation(kb_name):
    from app.services.vector_store_manager import vector_store_manager

    kb_b = kb_name.replace("itest_", "itestB_")
    try:
        vector_store_manager.ensure_partition(kb_name)
        vector_store_manager.ensure_partition(kb_b)
        vector_store_manager.add_documents_to_partition(
            [Document(page_content="cheese pizza", metadata={"note_id": "a"})],
            kb_name,
        )
        vector_store_manager.add_documents_to_partition(
            [Document(page_content="green tea", metadata={"note_id": "b"})],
            kb_b,
        )
        hits_a = vector_store_manager.similarity_search_in_partition(
            "pizza", kb_name, k=3)
        hits_b = vector_store_manager.similarity_search_in_partition(
            "pizza", kb_b, k=3)
        a_contents = [h.page_content for h in hits_a]
        b_contents = [h.page_content for h in hits_b]
        assert "cheese pizza" in a_contents
        assert "cheese pizza" not in b_contents
    finally:
        vector_store_manager.drop_kb_partition(kb_b)


def test_list_and_drop(kb_name):
    from app.services.vector_store_manager import vector_store_manager

    vector_store_manager.ensure_partition(kb_name, description="for-list")
    listed = vector_store_manager.list_kb_partitions()
    names = {x["kb_name"] for x in listed}
    assert kb_name in names

    n = vector_store_manager.drop_kb_partition(kb_name)
    assert n >= 0

    listed_after = vector_store_manager.list_kb_partitions()
    names_after = {x["kb_name"] for x in listed_after}
    assert kb_name not in names_after


def test_kb_not_found_raises():
    from app.services.vector_store_manager import (
        vector_store_manager, KBNotFoundError,
    )
    with pytest.raises(KBNotFoundError):
        vector_store_manager.similarity_search_in_partition(
            "q", "xhs_never_exists_00000000_000000", k=3,
        )
```

- [ ] **Step 10.2: 跑测试（环境默认跳过）**

Run: `pytest tests/services/test_vector_store_partition_integration.py -v`
Expected: 4 skipped

如本地有 Milvus 跑（端口 19530），可加环境变量验证：

Run: `RUN_MILVUS_TESTS=1 pytest tests/services/test_vector_store_partition_integration.py -v`
（Windows PowerShell: `$env:RUN_MILVUS_TESTS="1"; pytest ...`）
Expected: 4 passed

- [ ] **Step 10.3: Commit**

```bash
git add tests/services/test_vector_store_partition_integration.py
git commit -m "test(vector-store): add Milvus integration tests for partition isolation"
```

---

## Task 11: 端到端手测验证

无新代码；按以下顺序手测，全部通过后整套功能交付。

- [ ] **Step 11.1: 启动 XHS MCP Server**

新 PowerShell 窗口：

Run: `python mcp_servers/xhs_server.py`
Expected: 看到 "Uvicorn running on http://0.0.0.0:8013"

- [ ] **Step 11.2: 启动主服务**

另一个窗口：

Run: `python -m uvicorn app.main:app --port 9900`
Expected: 看到 SuperBizAgent 启动日志 + Milvus 连接成功 + collection 'biz' 已加载

- [ ] **Step 11.3: 入库一条成都数据**

Run（PowerShell）：

```powershell
curl.exe -X POST http://localhost:9900/api/xhs/ingest/mcp -H "Content-Type: application/json" -d '{\"keyword\":\"美食\",\"city\":\"成都\",\"count\":5}'
```

Expected: 返回 `code:200`，`data.kb_name` 形如 `xhs_<hex>_<ts>`，`chunks > 0`。
**记下 kb_name**，下面要用。

- [ ] **Step 11.4: 列出知识库**

Run: `curl.exe http://localhost:9900/api/xhs/kb/list`
Expected: `data.kbs` 至少含 11.3 中的 kb_name，`description="美食|成都"`，`created_at` 有值。

- [ ] **Step 11.5: 阻塞 RAG 对话**

把 `<KB>` 替换为 11.3 的 kb_name：

```powershell
curl.exe -X POST http://localhost:9900/api/chat/rag -H "Content-Type: application/json" -d "{\"Question\":\"成都必吃的几个美食推荐?\",\"session_id\":\"smoke-1\",\"kb_name\":\"<KB>\"}"
```

Expected:
- `data.answer` 中应出现 mock 数据里的菜名（郫县豆瓣鱼 / 夫妻肺片 / 龙抄手 / 担担面 等之一）
- `data.citations` 至少 1 条，包含 title、url、author、likes
- `data.hit_count >= 1`

- [ ] **Step 11.6: SSE 流式 RAG**

```powershell
curl.exe -N -X POST http://localhost:9900/api/chat/rag_stream -H "Content-Type: application/json" -d "{\"Question\":\"成都3日游怎么安排?\",\"session_id\":\"smoke-2\",\"kb_name\":\"<KB>\"}"
```

Expected:
- 第一行 `data: {"type":"citations", ...}`
- 中间若干 `data: {"type":"content", "data":"..."}`
- 最后 `data: {"type":"done"}`

- [ ] **Step 11.7: 错误 kb_name → 404**

```powershell
curl.exe -X POST http://localhost:9900/api/chat/rag -H "Content-Type: application/json" -d "{\"Question\":\"q\",\"kb_name\":\"xhs_doesnotexist_00000000_000000\"}"
```

Expected: `code:404`

- [ ] **Step 11.8: 删除知识库**

```powershell
curl.exe -X DELETE http://localhost:9900/api/xhs/kb/<KB>
```

Expected: `code:200`，`deleted_entities` > 0。
再调一次 `kb/list`，<KB> 应消失。

- [ ] **Step 11.9: 原 /chat 接口不受影响**

```powershell
curl.exe -X POST http://localhost:9900/api/chat -H "Content-Type: application/json" -d "{\"Question\":\"你好\",\"session_id\":\"plain-1\"}"
```

Expected: 正常返回，不依赖任何 kb。

- [ ] **Step 11.10: 全量自动化测试再跑一遍**

Run: `pytest tests/ -v`
Expected: 全 passed（或集成测试 4 skipped）。

如全部步骤通过，本计划完成。
