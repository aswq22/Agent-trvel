"""tests for rag_service.build_rag_context"""

import sys
from unittest.mock import patch

import pytest
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, SystemMessage


@pytest.fixture(scope="module", autouse=True)
def _load_rag_module():
    """First-load rag_service with Milvus mocked so VectorStoreManager
    singleton doesn't dial a real cluster."""
    if "app.services.rag_service" not in sys.modules:
        with patch("app.core.milvus_client.milvus_manager"), \
             patch("langchain_milvus.Milvus"):
            from app.services import rag_service  # noqa: F401
    yield


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

    sys_msg = ctx.messages[0]
    assert isinstance(sys_msg, SystemMessage)
    assert "参考资料" in sys_msg.content
    assert "郫县豆瓣鱼" in sys_msg.content

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
        with pytest.raises(KBNotFoundError):
            rag_service.build_rag_context("q", history=[],
                                          kb_name="xhs_missing", top_k=3)
