# tests/db/test_share_store.py
import pytest
from unittest.mock import patch


@pytest.fixture(autouse=True)
def use_temp_db(tmp_path):
    """Redirect share store to a temp SQLite DB for each test."""
    db_url = f"sqlite:///{tmp_path}/test_shares.db"
    import app.db.share_store as store
    with patch.object(store, "_engine", store.create_engine(
        db_url, connect_args={"check_same_thread": False}
    )):
        store.Base.metadata.create_all(store._engine)
        yield
        store.Base.metadata.drop_all(store._engine)


def test_save_and_get_share():
    from app.db.share_store import save_share, get_share

    share_id = save_share("# 成都攻略\n内容", {"days": [{"day": 1}], "total_cost": 2000.0, "tips": []})
    assert share_id

    result = get_share(share_id)
    assert result is not None
    assert result["plan"] == "# 成都攻略\n内容"
    assert result["structured_plan"]["total_cost"] == 2000.0


def test_get_share_not_found():
    from app.db.share_store import get_share

    result = get_share("00000000-0000-0000-0000-000000000000")
    assert result is None


def test_save_share_returns_unique_ids():
    from app.db.share_store import save_share

    id1 = save_share("plan1", {})
    id2 = save_share("plan2", {})
    assert id1 != id2
