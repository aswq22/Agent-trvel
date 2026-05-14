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
