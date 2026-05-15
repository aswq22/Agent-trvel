"""tests for /api/chat/rag and /api/chat/rag_stream"""

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage


@pytest.fixture(scope="module")
def chat_rag_module():
    """First-load chat_rag with Milvus mocked."""
    if "app.api.chat_rag" not in sys.modules:
        with patch("app.core.milvus_client.milvus_manager"), \
             patch("langchain_milvus.Milvus"):
            from app.api import chat_rag  # noqa: F401
    from app.api import chat_rag
    return chat_rag


@pytest.fixture
def client(chat_rag_module):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(chat_rag_module.router, prefix="/api")
    return TestClient(app)


def _ctx_with_hits():
    from app.services.rag_service import RagContext, Citation
    return RagContext(
        messages=[],
        citations=[Citation(title="T", url="u", author="a", likes=9)],
        hit_count=1,
    )


def test_chat_rag_missing_kb_name_falls_back_to_global(client):
    """v2: 未传 kb_name 不再返 400，而是走全局检索（build_rag_context kb_name=None）"""
    from langchain_core.messages import AIMessage
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=AIMessage(content="全局答案"))
    with patch("app.api.chat_rag.build_rag_context", return_value=_ctx_with_hits()) as build_ctx, \
         patch("app.api.chat_rag.LLMFactory.create_travel_llm", return_value=fake_llm), \
         patch("app.api.chat_rag.session_store") as ss:
        ss.get.return_value = []
        resp = client.post("/api/chat/rag",
                           json={"Question": "q", "session_id": "s1"})
    body = resp.json()
    assert body["code"] == 200
    assert body["data"]["answer"] == "全局答案"
    # build_rag_context 调用时 kb_name 应该是空字符串（来自 RagChatRequest 默认）
    _, kwargs = build_ctx.call_args
    assert kwargs.get("kb_name") == "" or kwargs.get("kb_name") is None


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
