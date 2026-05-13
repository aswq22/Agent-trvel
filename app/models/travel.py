# app/models/travel.py
from typing import Optional
from pydantic import BaseModel, Field
from app.agent.travel.state import TripParams


class TripRequest(BaseModel):
    user_input: str = Field(default="", description="自然语言旅行需求描述")
    trip_params: Optional[TripParams] = Field(default=None, description="结构化旅行参数（优先级高于 user_input）")
    session_id: str = Field(default="default", description="会话ID")

    class Config:
        json_schema_extra = {
            "example": {
                "user_input": "帮我规划一个五天四夜的成都之旅，预算5000元，喜欢吃辣和历史文化",
                "session_id": "session-001"
            }
        }


class ShareRequest(BaseModel):
    plan: str = Field(description="Markdown 攻略文本")
    structured_plan: dict = Field(default_factory=dict, description="结构化攻略 JSON")


class ShareResponse(BaseModel):
    share_id: str
    url: str
