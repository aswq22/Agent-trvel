"""单元测试：VectorStoreManager 的 partition 管理方法（mock collection）

测试不依赖真 Milvus 服务：fixture 会清掉 vector_store_manager 模块缓存，
patch 掉它依赖的 milvus_manager 和 langchain_milvus.Milvus，再重新 import。
"""

import sys
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
    """patch 依赖后强制重新 import vector_store_manager 模块。"""
    fake_mm = MagicMock()
    fake_mm.connect.return_value = MagicMock()
    fake_mm.get_collection.return_value = fake_collection

    # 移除已 cache 的失败/旧模块
    sys.modules.pop("app.services.vector_store_manager", None)

    with patch("app.core.milvus_client.milvus_manager", fake_mm), \
         patch("langchain_milvus.Milvus", MagicMock()):
        import app.services.vector_store_manager as mod  # noqa: WPS433
        yield mod.vector_store_manager

    # 清理，避免污染后续测试
    sys.modules.pop("app.services.vector_store_manager", None)


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
    p_xhs = MagicMock(num_entities=42, description="美食|成都")
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
