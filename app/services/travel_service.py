# app/services/travel_service.py
from typing import AsyncGenerator, Dict, Any, Optional
from loguru import logger

from app.agent.travel.graph import build_travel_graph, make_initial_state
from app.agent.travel.state import TripParams


class TravelService:

    def __init__(self):
        self._graph = build_travel_graph()
        logger.info("TravelService 初始化完成")

    async def plan(
        self,
        user_input: str = "",
        trip_params: Optional[TripParams] = None,
        session_id: str = "default",
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """Execute travel planning, yielding SSE progress events."""
        initial = make_initial_state(user_input)
        if trip_params:
            initial["trip_params"] = trip_params
            if not user_input:
                initial["user_input"] = f"规划{trip_params.destination}{trip_params.days}日游"

        logger.info(f"[会话 {session_id}] 开始旅游规划: {user_input or trip_params}")
        config_dict = {"configurable": {"thread_id": session_id}}

        try:
            async for event in self._graph.astream(
                input=initial,
                config=config_dict,
                stream_mode="updates",
            ):
                for node_name, node_output in event.items():
                    yield self._format_event(node_name, node_output)

            final_state = self._graph.get_state(config_dict)
            final_plan = ""
            structured_plan = None
            if final_state and final_state.values:
                final_plan = final_state.values.get("final_plan", "")
                structured_plan = final_state.values.get("structured_plan")

            yield {
                "type": "complete",
                "message": "规划完成" if final_plan else "规划完成（无攻略输出）",
                "final_plan": final_plan,
                "structured_plan": structured_plan,
            }
            logger.info(f"[会话 {session_id}] 规划完成")

        except Exception as e:
            logger.error(f"[会话 {session_id}] 规划失败: {e}", exc_info=True)
            yield {"type": "error", "message": f"规划出错: {str(e)}"}

    @staticmethod
    def _format_event(node_name: str, output: dict | None) -> Dict[str, Any]:
        _LABELS = {
            "parser": ("parsing", "解析旅行参数..."),
            "attraction_agent": ("attractions", "正在搜索景点..."),
            "route_agent": ("route", "正在规划路线..."),
            "hotel_agent": ("hotels", "正在搜索酒店..."),
            "food_agent": ("food", "正在推荐美食..."),
            "strategy_agent": ("strategy", "正在生成完整攻略..."),
        }
        stage, message = _LABELS.get(node_name, (node_name, f"{node_name} 执行中"))
        event: Dict[str, Any] = {"type": "progress", "stage": stage, "message": message}
        if output:
            if node_name == "strategy_agent" and output.get("final_plan"):
                event["content"] = output["final_plan"]
            if node_name == "attraction_agent" and output.get("attractions"):
                event["attractions"] = output["attractions"]
        return event


travel_service = TravelService()
