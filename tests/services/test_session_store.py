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
    session_store.clear("never-existed")
    assert session_store.get("never-existed") == []


def test_sessions_are_isolated():
    session_store.append("a", "user", "hi-a")
    session_store.append("b", "user", "hi-b")
    assert session_store.get("a") == [{"role": "user", "content": "hi-a"}]
    assert session_store.get("b") == [{"role": "user", "content": "hi-b"}]
