# app/api/xhs.py
# 小红书 RAG 管理接口
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.xhs_ingestion_service import ingest_from_mcp, ingest_raw_text
from app.core.milvus_client import milvus_manager

router = APIRouter()


class RawIngestRequest(BaseModel):
    title: str
    content: str
    city: str = ""
    tags: List[str] = []


class McpIngestRequest(BaseModel):
    keyword: str = "旅游攻略"
    city: str = ""
    count: int = 10


@router.post("/xhs/ingest/text")
async def ingest_text(body: RawIngestRequest):
    """手动粘贴小红书内容入库（无需 MCP）"""
    result = ingest_raw_text(
        title=body.title,
        content=body.content,
        city=body.city,
        tags=body.tags,
    )
    return {"code": 200, "message": "入库成功", "data": result}


@router.post("/xhs/ingest/mcp")
async def ingest_mcp(body: McpIngestRequest):
    """通过 XHS MCP 搜索并批量入库（需启动 xhs_server.py）"""
    try:
        result = await ingest_from_mcp(
            keyword=body.keyword,
            city=body.city,
            count=body.count,
        )
        return {"code": 200, "message": "入库成功", "data": result}
    except Exception as e:
        return {"code": 500, "message": f"MCP 连接失败: {e}", "data": None}


@router.get("/xhs/stats")
async def xhs_stats():
    """查看 Milvus 中的 XHS 数据统计"""
    try:
        collection = milvus_manager.get_collection()
        total = collection.num_entities
        return {
            "code": 200,
            "data": {
                "total_vectors": total,
                "collection": "biz",
                "note": "所有来源（XHS + 其他文档）共用 biz collection",
            },
        }
    except Exception as e:
        return {"code": 500, "message": str(e), "data": None}
