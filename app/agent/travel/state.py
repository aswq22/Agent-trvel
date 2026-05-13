from typing import List, TypedDict, Annotated, Optional
from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class TripParams(BaseModel):
    destination: str = Field(description="目的地城市，如'成都'")
    start_date: str = Field(default="", description="出发日期，格式 YYYY-MM-DD")
    days: int = Field(default=3, description="出行天数")
    num_people: int = Field(default=2, description="出行人数")
    budget: float = Field(default=3000.0, description="总预算（元）")
    preferences: List[str] = Field(default_factory=list, description="偏好标签")
    language: str = Field(default="zh", description="输出语言: zh 或 en")


def merge_dicts(existing: dict, new: dict) -> dict:
    return {**existing, **new}


class TravelPlanState(TypedDict):
    user_input: str
    trip_params: Optional[TripParams]
    attractions: List[dict]
    route: dict
    hotels: List[dict]
    foods: List[dict]
    final_plan: str
    structured_plan: Optional[dict]
    errors: Annotated[dict, merge_dicts]
    messages: Annotated[List[BaseMessage], add_messages]
