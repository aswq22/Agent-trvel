# app/api/xhs.py
# 小红书 RAG 管理接口
import re
from typing import List, Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.xhs_ingestion_service import ingest_from_mcp, ingest_raw_text
from app.services.vector_store_manager import vector_store_manager
from app.core.milvus_client import milvus_manager

router = APIRouter()

# Milvus partition 名约束：字母数字下划线，最长 255
_KB_NAME_RE = re.compile(r"^xhs_[a-zA-Z0-9_]{1,240}$")


class RawIngestRequest(BaseModel):
    title: str
    content: str
    city: str = ""
    tags: List[str] = []
    kb_name: Optional[str] = None


class McpIngestRequest(BaseModel):
    keyword: str = "旅游攻略"
    city: str = ""
    count: int = 10


def _parse_created_at(kb_name: str) -> str:
    """从 xhs_<hex>_YYYYMMDD_HHMMSS 末尾解析时间，失败返空串。"""
    parts = kb_name.split("_")
    if len(parts) < 4:
        return ""
    date, time_ = parts[-2], parts[-1]
    if len(date) == 8 and len(time_) == 6 and date.isdigit() and time_.isdigit():
        return f"{date[:4]}-{date[4:6]}-{date[6:8]} {time_[:2]}:{time_[2:4]}:{time_[4:6]}"
    return ""


@router.post("/xhs/ingest/text")
async def ingest_text(body: RawIngestRequest):
    """手动粘贴小红书内容入库（无需 MCP）"""
    if body.kb_name and not _KB_NAME_RE.match(body.kb_name):
        return {"code": 400,
                "message": "kb_name 必须满足 ^xhs_[a-zA-Z0-9_]{1,240}$",
                "data": None}
    result = ingest_raw_text(
        title=body.title,
        content=body.content,
        city=body.city,
        tags=body.tags,
        kb_name=body.kb_name,
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


@router.get("/xhs/kb/list")
async def kb_list():
    """列出所有 xhs_ 开头的知识库分区。"""
    try:
        kbs = vector_store_manager.list_kb_partitions()
        for kb in kbs:
            kb["created_at"] = _parse_created_at(kb["kb_name"])
        return {"code": 200, "data": {"total": len(kbs), "kbs": kbs}}
    except Exception as e:
        return {"code": 500, "message": str(e), "data": None}


@router.delete("/xhs/kb/{kb_name}")
async def kb_delete(kb_name: str):
    """删除指定知识库分区。"""
    if not _KB_NAME_RE.match(kb_name):
        return {"code": 400, "message": "kb_name 格式非法", "data": None}
    try:
        n = vector_store_manager.drop_kb_partition(kb_name)
        if n == -1:
            return {"code": 404,
                    "message": f"知识库 '{kb_name}' 不存在", "data": None}
        return {"code": 200, "data": {"kb_name": kb_name, "deleted_entities": n}}
    except Exception as e:
        return {"code": 500, "message": str(e), "data": None}


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
