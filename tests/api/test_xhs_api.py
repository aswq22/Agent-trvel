"""tests for /api/xhs/* endpoints"""

import sys
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def xhs_module():
    """First-load 'app.api.xhs' with Milvus mocked so the singleton inside
    'vector_store_manager' doesn't try to dial a real cluster.

    Once loaded, the module stays in sys.modules; individual tests patch
    `app.api.xhs.vector_store_manager` / `app.api.xhs.ingest_from_mcp` etc.
    """
    if "app.api.xhs" not in sys.modules:
        with patch("app.core.milvus_client.milvus_manager"), \
             patch("langchain_milvus.Milvus"):
            from app.api import xhs  # noqa: F401  (triggers cached load)
    from app.api import xhs
    return xhs


@pytest.fixture
def client(xhs_module):
    from fastapi import FastAPI
    app = FastAPI()
    app.include_router(xhs_module.router, prefix="/api")
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
    assert resp.status_code == 200
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
