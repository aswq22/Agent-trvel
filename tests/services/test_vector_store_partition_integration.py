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
    name = f"xhs_itest_{uuid.uuid4().hex[:8]}_20260514_120000"
    yield name
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
