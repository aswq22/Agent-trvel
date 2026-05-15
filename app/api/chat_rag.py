"""RAG 对话 API — /chat/rag 阻塞 + /chat/rag_stream SSE"""

import json
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from loguru import logger
from pydantic import BaseModel

from app.config import config
from app.core.llm_factory import LLMFactory
from app.services import session_store
from app.services.rag_service import build_rag_context
from app.services.vector_store_manager import KBNotFoundError

router = APIRouter()


class RagChatRequest(BaseModel):
    Question: str = ""
    session_id: Optional[str] = "default"
    # 可选；None / 空字符串 → 跨所有 xhs_* partition 全局检索
    kb_name: Optional[str] = ""
    top_k: Optional[int] = None


def _sid(req: RagChatRequest) -> str:
    return req.session_id or "default"


def _validate(req: RagChatRequest):
    if not req.Question.strip():
        return {"code": 400, "message": "Question 不能为空", "data": None}
    # kb_name 可选；空字符串等价于"全部知识库"
    return None


@router.post("/chat/rag")
async def chat_rag(request: RagChatRequest):
    err = _validate(request)
    if err:
        return err

    sid = _sid(request)
    history = session_store.get(sid)
    top_k = request.top_k or config.rag_top_k

    try:
        ctx = build_rag_context(
            question=request.Question,
            history=history,
            kb_name=request.kb_name,
            top_k=top_k,
        )
    except KBNotFoundError as e:
        return {"code": 404, "message": str(e), "data": None}
    except Exception as e:
        logger.exception("build_rag_context error: {}", repr(e))
        return {"code": 500, "message": str(e), "data": None}

    try:
        llm = LLMFactory.create_travel_llm(temperature=0.7, streaming=False)
        resp = await llm.ainvoke(ctx.messages)
        answer = resp.content
    except Exception as e:
        logger.exception("llm error: {}", repr(e))
        return {"code": 500, "message": str(e),
                "data": {"success": False, "answer": None,
                         "errorMessage": str(e)}}

    session_store.append(sid, "user", request.Question)
    session_store.append(sid, "assistant", answer)

    return {
        "code": 200,
        "message": "success",
        "data": {
            "success": True,
            "answer": answer,
            "citations": [asdict(c) for c in ctx.citations],
            "hit_count": ctx.hit_count,
            "errorMessage": None,
        },
    }


@router.post("/chat/rag_stream")
async def chat_rag_stream(request: RagChatRequest):
    err = _validate(request)
    sid = _sid(request)

    async def generate():
        if err:
            yield f"data: {json.dumps({'type':'error','data':err['message']}, ensure_ascii=False)}\n\n"
            return

        history = session_store.get(sid)
        top_k = request.top_k or config.rag_top_k

        try:
            ctx = build_rag_context(
                question=request.Question,
                history=history,
                kb_name=request.kb_name,
                top_k=top_k,
            )
        except KBNotFoundError as e:
            yield f"data: {json.dumps({'type':'error','data':str(e)}, ensure_ascii=False)}\n\n"
            return
        except Exception as e:
            logger.exception("build_rag_context error: {}", repr(e))
            yield f"data: {json.dumps({'type':'error','data':str(e)}, ensure_ascii=False)}\n\n"
            return

        citations_payload = [asdict(c) for c in ctx.citations]
        yield f"data: {json.dumps({'type':'citations','data':citations_payload}, ensure_ascii=False)}\n\n"

        full = ""
        try:
            llm = LLMFactory.create_travel_llm(temperature=0.7, streaming=True)
            async for chunk in llm.astream(ctx.messages):
                content = chunk.content if hasattr(chunk, "content") else str(chunk)
                if content:
                    full += content
                    yield f"data: {json.dumps({'type':'content','data':content}, ensure_ascii=False)}\n\n"
        except Exception as e:
            logger.exception("llm stream error: {}", repr(e))
            yield f"data: {json.dumps({'type':'error','data':str(e)}, ensure_ascii=False)}\n\n"
            return

        session_store.append(sid, "user", request.Question)
        session_store.append(sid, "assistant", full)
        yield f"data: {json.dumps({'type':'done'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
