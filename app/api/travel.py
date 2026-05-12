# app/api/travel.py
import json
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse
from loguru import logger

from app.models.travel import TripRequest
from app.services.travel_service import travel_service

router = APIRouter()


@router.post("/travel/plan")
async def plan_trip(request: TripRequest):
    """
    旅游规划接口（流式 SSE）

    支持两种输入方式：
    1. 自然语言：`{"user_input": "帮我规划5天成都之旅，预算5000元"}`
    2. 结构化：`{"trip_params": {"destination": "成都", "days": 5, "budget": 5000}}`

    **SSE 事件类型：**
    - `progress` — Agent 进度
    - `complete` — 规划完成，含 `final_plan`
    - `error` — 错误信息
    """
    session_id = request.session_id or "default"
    logger.info(f"[会话 {session_id}] 收到旅游规划请求")

    async def event_generator():
        try:
            async for event in travel_service.plan(
                user_input=request.user_input,
                trip_params=request.trip_params,
                session_id=session_id,
            ):
                yield {"event": "message", "data": json.dumps(event, ensure_ascii=False)}
                if event.get("type") in ("complete", "error"):
                    break
        except Exception as e:
            logger.error(f"[会话 {session_id}] SSE 异常: {e}", exc_info=True)
            yield {
                "event": "message",
                "data": json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False),
            }

    return EventSourceResponse(event_generator())
