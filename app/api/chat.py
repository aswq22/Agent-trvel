"""聊天 API — 基于 LLMFactory 的简单对话接口"""

import json
from typing import Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from loguru import logger
from pydantic import BaseModel

from app.core.llm_factory import LLMFactory

router = APIRouter()

_SYSTEM_PROMPT = (
    "你是一个智能旅游助手，也可以回答各种日常问题。"
    "请用友好、简洁的方式用中文回复用户。"
)

# 内存会话存储：{session_id: [{role, content}, ...]}
_sessions: Dict[str, List[dict]] = {}


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
    """聊天 LLM：与旅游 Agent 使用同一套配置（DeepSeek 优先，fallback DashScope）。"""
    return LLMFactory.create_travel_llm(temperature=0.7, streaming=streaming)


@router.post("/chat")
async def chat(request: ChatRequest):
    sid = _sid(request)
    q = _question(request)
    if not q:
        return {"code": 400, "message": "问题不能为空", "data": None}

    history = _sessions.setdefault(sid, [])
    msgs = _build_lc_messages(history, q)

    try:
        response = await _make_llm().ainvoke(msgs)
        answer = response.content
        history.append({"role": "user", "content": q})
        history.append({"role": "assistant", "content": answer})
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
    history = _sessions.setdefault(sid, [])
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
            history.append({"role": "user", "content": q})
            history.append({"role": "assistant", "content": full_response})
            yield f"data: {json.dumps({'type': 'done'}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("chat_stream error: {}", repr(e))
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/chat/session/{session_id}")
async def get_session(session_id: str):
    history = _sessions.get(session_id, [])
    return {"history": history, "session_id": session_id, "message_count": len(history)}


@router.post("/chat/clear")
async def clear_session(request: ClearRequest):
    sid = request.session_id or request.sessionId
    _sessions.pop(sid, None)
    return {"status": "success", "message": "会话已清空"}
