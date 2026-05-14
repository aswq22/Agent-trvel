"""RAG 上下文构造：检索 + prompt 拼接 + citations 去重。"""

from dataclasses import dataclass
from typing import List

from langchain_core.documents import Document
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from loguru import logger

from app.services.vector_store_manager import vector_store_manager


@dataclass
class Citation:
    title: str
    url: str
    author: str
    likes: int


@dataclass
class RagContext:
    messages: List[BaseMessage]
    citations: List[Citation]
    hit_count: int


_SYSTEM_PROMPT_WITH_CONTEXT = """你是一个智能旅游助手。请基于下面的小红书攻略参考资料回答用户问题。
- 优先使用参考资料中的信息
- 如果参考资料不足，可以基于通用常识补充，但要明确标注"以下为通用建议"
- 不要编造资料里没有的具体地名/价格/路线

【参考资料】
{context_block}
"""

_SYSTEM_PROMPT_NO_HIT = """你是一个智能旅游助手。指定知识库中未检索到与本问题相关的内容，请基于通用常识简洁回答用户问题，并在开头注明"以下为通用建议"。"""


def _format_context(docs: List[Document]) -> str:
    blocks = []
    for i, d in enumerate(docs, 1):
        md = d.metadata or {}
        title = md.get("_file_name", "")
        author = md.get("author", "")
        likes = md.get("likes", 0)
        blocks.append(
            f"[{i}] 标题：{title}（作者：{author}，{likes} 赞）\n    内容：{d.page_content}"
        )
    return "\n".join(blocks)


def _extract_citations(docs: List[Document]) -> List[Citation]:
    seen = set()
    out: List[Citation] = []
    for d in docs:
        md = d.metadata or {}
        nid = md.get("note_id", "")
        if not nid or nid in seen:
            continue
        seen.add(nid)
        out.append(Citation(
            title=md.get("_file_name", ""),
            url=md.get("_source", ""),
            author=md.get("author", ""),
            likes=md.get("likes", 0),
        ))
    return out


def _history_to_lc(history: List[dict]) -> List[BaseMessage]:
    msgs: List[BaseMessage] = []
    for h in history[-20:]:
        if h["role"] == "user":
            msgs.append(HumanMessage(content=h["content"]))
        else:
            msgs.append(AIMessage(content=h["content"]))
    return msgs


def build_rag_context(
    question: str,
    history: List[dict],
    kb_name: str,
    top_k: int = 3,
) -> RagContext:
    """检索 kb_name → 构造 messages + citations。

    KB 不存在时抛 KBNotFoundError（来自 vector_store_manager）。
    """
    docs = vector_store_manager.similarity_search_in_partition(
        query=question, kb_name=kb_name, k=top_k,
    )
    logger.info(f"RAG kb='{kb_name}' query='{question[:30]}' hits={len(docs)}")

    if docs:
        sys_content = _SYSTEM_PROMPT_WITH_CONTEXT.format(
            context_block=_format_context(docs)
        )
    else:
        sys_content = _SYSTEM_PROMPT_NO_HIT

    messages: List[BaseMessage] = [SystemMessage(content=sys_content)]
    messages.extend(_history_to_lc(history))
    messages.append(HumanMessage(content=question))

    return RagContext(
        messages=messages,
        citations=_extract_citations(docs),
        hit_count=len(docs),
    )
