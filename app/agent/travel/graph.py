# app/agent/travel/graph.py
from typing import List
from langgraph.graph import StateGraph, END
from langgraph.types import Send
from langgraph.checkpoint.memory import MemorySaver
from loguru import logger

from app.agent.travel.state import TravelPlanState
from app.agent.travel.parser import parser_node
from app.agent.travel.attraction import attraction_node
from app.agent.travel.route import route_node
from app.agent.travel.hotel import hotel_node
from app.agent.travel.food import food_node
from app.agent.travel.strategy import strategy_node


def _dispatch_parallel(state: TravelPlanState) -> List[Send]:
    """Phase 2: After AttractionAgent, fan-out to Route/Hotel/Food in parallel."""
    logger.info("并行派发 Route/Hotel/Food Agent")
    return [
        Send("route_agent", state),
        Send("hotel_agent", state),
        Send("food_agent", state),
    ]


def build_travel_graph():
    """Build 3-phase travel planning graph."""
    workflow = StateGraph(TravelPlanState)

    workflow.add_node("parser", parser_node)
    workflow.add_node("attraction_agent", attraction_node)
    workflow.add_node("route_agent", route_node)
    workflow.add_node("hotel_agent", hotel_node)
    workflow.add_node("food_agent", food_node)
    workflow.add_node("strategy_agent", strategy_node)

    # Phase 1: serial
    workflow.set_entry_point("parser")
    workflow.add_edge("parser", "attraction_agent")

    # Phase 2: parallel fan-out via Send()
    workflow.add_conditional_edges(
        "attraction_agent",
        _dispatch_parallel,
        ["route_agent", "hotel_agent", "food_agent"],
    )

    # Phase 3: fan-in to strategy (waits for all parallel branches)
    workflow.add_edge("route_agent", "strategy_agent")
    workflow.add_edge("hotel_agent", "strategy_agent")
    workflow.add_edge("food_agent", "strategy_agent")
    workflow.add_edge("strategy_agent", END)

    return workflow.compile(checkpointer=MemorySaver())


def make_initial_state(user_input: str) -> TravelPlanState:
    return {
        "user_input": user_input,
        "trip_params": None,
        "attractions": [],
        "route": {},
        "hotels": [],
        "foods": [],
        "final_plan": "",
        "errors": {},
        "messages": [],
    }
