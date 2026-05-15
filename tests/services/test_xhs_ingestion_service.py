"""tests for xhs_ingestion_service"""

import re
import sys
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def _isolate_vsm():
    """xhs_ingestion_service 内会 import vector_store_manager；
    强制重 import 时用 mock 替换，避免连真 Milvus。"""
    sys.modules.pop("app.services.xhs_ingestion_service", None)
    sys.modules.pop("app.services.vector_store_manager", None)

    fake_vsm = type("FakeVSM", (), {})()
    fake_vsm.ensure_partition = lambda *a, **kw: None
    fake_vsm.add_documents_to_partition = lambda docs, kb: ["id-x"] * len(docs)

    with patch("app.core.milvus_client.milvus_manager"), \
         patch("langchain_milvus.Milvus"):
        # 强制模块重新加载
        import app.services.xhs_ingestion_service as svc
        # 然后再次 patch 内部引用
        svc.vector_store_manager = fake_vsm
        yield svc

    sys.modules.pop("app.services.xhs_ingestion_service", None)
    sys.modules.pop("app.services.vector_store_manager", None)


def test_make_kb_name_format_city_only(_isolate_vsm):
    svc = _isolate_vsm
    name = svc._make_kb_name("成都")
    assert re.match(r"^xhs_[0-9a-f]{8}$", name)


def test_make_kb_name_empty_city_returns_global(_isolate_vsm):
    svc = _isolate_vsm
    assert svc._make_kb_name("") == "xhs_global"
    assert svc._make_kb_name("   ") == "xhs_global"
    assert svc._make_kb_name(None) == "xhs_global"


def test_make_kb_name_deterministic_per_city(_isolate_vsm):
    """同 city 永远映射到同一 partition（无时间戳分量）。"""
    svc = _isolate_vsm
    assert svc._make_kb_name("成都") == svc._make_kb_name("成都")
    # 不同 city 产生不同 hash
    assert svc._make_kb_name("成都") != svc._make_kb_name("北京")
    # 前后空格不影响
    assert svc._make_kb_name("成都") == svc._make_kb_name("  成都  ")


def test_ingest_notes_creates_partition_and_inserts(_isolate_vsm):
    svc = _isolate_vsm
    calls = {}
    svc.vector_store_manager.ensure_partition = lambda kb, description="": calls.setdefault("ensure", (kb, description))
    svc.vector_store_manager.add_documents_to_partition = lambda docs, kb: ["id-1"]

    notes = [{
        "note_id": "n1", "title": "T", "content": "C" * 50,
        "city": "成都", "tags": ["美食"], "author": "a", "url": "u", "likes": 9,
    }]
    result = svc.ingest_notes(notes, kb_name="xhs_test_20260514_120000",
                              description="t|c")
    assert result == {"ingested": 1, "chunks": 1}
    assert calls["ensure"] == ("xhs_test_20260514_120000", "t|c")


def test_ingest_notes_empty_does_not_create_partition(_isolate_vsm):
    svc = _isolate_vsm
    flag = {"called": False}
    svc.vector_store_manager.ensure_partition = lambda *a, **kw: flag.__setitem__("called", True)
    result = svc.ingest_notes([], kb_name="xhs_x_20260514_120000", description="")
    assert result == {"ingested": 0, "chunks": 0}
    assert flag["called"] is False


@pytest.mark.asyncio
async def test_ingest_from_mcp_returns_kb_name(_isolate_vsm):
    svc = _isolate_vsm
    fake_notes = [{
        "note_id": "n1", "title": "T", "content": "X" * 100,
        "city": "成都", "tags": [], "author": "", "url": "", "likes": 0,
    }]
    svc.vector_store_manager.ensure_partition = lambda *a, **kw: None
    svc.vector_store_manager.add_documents_to_partition = lambda docs, kb: ["id-1"] * len(docs)

    with patch.object(svc, "_fetch_notes_from_mcp", new=AsyncMock(return_value=fake_notes)):
        result = await svc.ingest_from_mcp("k", "成都", count=3)

    assert result["kb_name"] is not None
    assert result["kb_name"].startswith("xhs_")
    assert result["ingested"] == 1


@pytest.mark.asyncio
async def test_ingest_from_mcp_zero_notes_returns_null_kb_name(_isolate_vsm):
    svc = _isolate_vsm
    flag = {"ensure_called": False}
    svc.vector_store_manager.ensure_partition = lambda *a, **kw: flag.__setitem__("ensure_called", True)

    with patch.object(svc, "_fetch_notes_from_mcp", new=AsyncMock(return_value=[])):
        result = await svc.ingest_from_mcp("k", "c", count=3)
    assert result["kb_name"] is None
    assert result["ingested"] == 0
    assert flag["ensure_called"] is False
