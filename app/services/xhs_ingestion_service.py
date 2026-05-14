# app/services/xhs_ingestion_service.py
# 小红书笔记入库管道：MCP 搜索 → 分块 → 向量化 → Milvus
import hashlib
from typing import Any, Dict, List

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from loguru import logger

from app.config import config
from app.services.vector_store_manager import vector_store_manager


_splitter = RecursiveCharacterTextSplitter(
    chunk_size=config.chunk_max_size,
    chunk_overlap=config.chunk_overlap,
)


def _note_to_docs(note: dict) -> List[Document]:
    """将一条 XHS 笔记拆分为 LangChain Document 列表"""
    full_text = f"【{note.get('title', '')}】\n{note.get('content', '')}"
    chunks = _splitter.split_text(full_text)
    docs = []
    for i, chunk in enumerate(chunks):
        docs.append(Document(
            page_content=chunk,
            metadata={
                "_source": note.get("url", "xhs"),
                "_file_name": note.get("title", "xhs_note"),
                "note_id": note.get("note_id", ""),
                "city": note.get("city", ""),
                "tags": ",".join(note.get("tags", [])),
                "author": note.get("author", ""),
                "likes": note.get("likes", 0),
                "chunk_index": i,
                "source_type": "xhs",
            },
        ))
    return docs


async def _fetch_notes_from_mcp(keyword: str, city: str, count: int) -> List[dict]:
    """通过 XHS MCP 搜索笔记"""
    from fastmcp import Client

    async with Client(config.mcp_xhs_url) as client:
        result = await client.call_tool(
            "xhs_search_notes",
            {"keyword": keyword, "city": city, "count": count},
        )
    # fastmcp 返回 list[TextContent]，取第一个的 text
    import json
    raw = result[0].text if result else "{}"
    data = json.loads(raw)
    return data.get("notes", [])


def ingest_notes(notes: List[dict]) -> Dict[str, Any]:
    """将笔记列表入库，返回入库统计"""
    if not notes:
        return {"ingested": 0, "chunks": 0}

    all_docs: List[Document] = []
    for note in notes:
        all_docs.extend(_note_to_docs(note))

    if not all_docs:
        return {"ingested": 0, "chunks": 0}

    ids = vector_store_manager.add_documents(all_docs)
    logger.info(f"XHS 入库完成: {len(notes)} 条笔记 → {len(ids)} 个向量块")
    return {"ingested": len(notes), "chunks": len(ids)}


async def ingest_from_mcp(keyword: str, city: str = "", count: int = 10) -> Dict[str, Any]:
    """从 XHS MCP 搜索并入库"""
    logger.info(f"XHS MCP 搜索入库: keyword={keyword}, city={city}, count={count}")
    notes = await _fetch_notes_from_mcp(keyword, city, count)
    result = ingest_notes(notes)
    result["keyword"] = keyword
    result["city"] = city
    return result


def ingest_raw_text(title: str, content: str, city: str = "", tags: list = None) -> Dict[str, Any]:
    """直接入库手动粘贴的 XHS 内容（无需 MCP）"""
    note = {
        "note_id": hashlib.md5(content.encode()).hexdigest()[:12],
        "title": title,
        "content": content,
        "city": city,
        "tags": tags or [],
        "author": "manual",
        "url": "manual",
        "likes": 0,
    }
    return ingest_notes([note])
