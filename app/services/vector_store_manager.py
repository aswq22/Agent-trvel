"""向量存储管理器 - 封装 Milvus VectorStore 操作"""

import uuid
from typing import List

from langchain_core.documents import Document
from langchain_milvus import Milvus
from loguru import logger

from app.config import config
from app.core.milvus_client import milvus_manager
from app.services.vector_embedding_service import vector_embedding_service


# 统一使用 biz collection
COLLECTION_NAME = "biz"


class KBNotFoundError(Exception):
    """请求的知识库（partition）不存在。"""


class VectorStoreManager:
    """向量存储管理器"""

    def __init__(self):
        """初始化向量存储管理器"""
        self.vector_store = None
        self.collection_name = COLLECTION_NAME
        self._initialize_vector_store()

    def _initialize_vector_store(self):
        """初始化 Milvus VectorStore"""
        try:
            # 必须在 PyMilvus / langchain_milvus 访问 Collection 之前建立连接，
            # 否则会出现 ConnectionNotExistException: should create connection first.
            # （模块导入时就会执行此处，早于 FastAPI lifespan 中的 milvus_manager.connect）
            _ = milvus_manager.connect()

            connection_args = {
                "host": config.milvus_host,
                "port": config.milvus_port,
            }

            # 创建 LangChain Milvus VectorStore
            # 使用 biz collection，字段映射：text_field -> content, vector_field -> vector
            self.vector_store = Milvus(
                embedding_function=vector_embedding_service,
                collection_name=self.collection_name,
                connection_args=connection_args,
                auto_id=False,  # 使用自定义 id
                drop_old=False,
                text_field="content",  # 文本内容存储到 content 字段
                vector_field="vector",  # 向量存储到 vector 字段
                primary_field="id",  # 主键字段
                metadata_field="metadata",  # 元数据字段
            )

            logger.info(
                f"VectorStore 初始化成功: {config.milvus_host}:{config.milvus_port}, "
                f"collection: {self.collection_name}"
            )

        except Exception as e:
            logger.error(f"VectorStore 初始化失败: {e}")
            raise

    def add_documents(self, documents: List[Document]) -> List[str]:
        """
        批量添加文档到向量存储（自动批量向量化）

        Args:
            documents: 文档列表

        Returns:
            List[str]: 文档 ID 列表
        """
        try:
            import time
            import uuid
            start_time = time.time()

            # 为每个文档生成唯一 id（因为 auto_id=False）
            ids = [str(uuid.uuid4()) for _ in documents]

            # LangChain Milvus 的 add_documents 会自动调用 embedding_function
            # 并进行批量处理，性能更好
            result_ids = self.vector_store.add_documents(documents, ids=ids)

            elapsed = time.time() - start_time
            logger.info(
                f"批量添加 {len(documents)} 个文档到 VectorStore 完成, "
                f"耗时: {elapsed:.2f}秒, 平均: {elapsed/len(documents):.2f}秒/个"
            )
            return result_ids
        except Exception as e:
            logger.error(f"添加文档失败: {e}")
            raise

    def delete_by_source(self, file_path: str) -> int:
        """
        删除指定文件的所有文档

        Args:
            file_path: 文件路径

        Returns:
            int: 删除的文档数量
        """
        try:
            # 使用 milvus_manager 获取已连接的 collection
            collection = milvus_manager.get_collection()
            
            # metadata 是 JSON 字段，使用 JSON 路径查询语法
            # _source 是文档的来源文件路径
            expr = f'metadata["_source"] == "{file_path}"'
            
            result = collection.delete(expr)
            deleted_count = result.delete_count if hasattr(result, "delete_count") else 0
            
            logger.info(f"删除文件旧数据: {file_path}, 删除数量: {deleted_count}")
            return deleted_count
            
        except Exception as e:
            logger.warning(f"删除旧数据失败 (可能是首次索引): {e}")
            return 0

    def get_vector_store(self) -> Milvus:
        """
        获取 VectorStore 实例

        Returns:
            Milvus: VectorStore 实例
        """
        return self.vector_store

    def similarity_search(self, query: str, k: int = 3) -> List[Document]:
        """
        相似度搜索

        Args:
            query: 查询文本
            k: 返回结果数量

        Returns:
            List[Document]: 相关文档列表
        """
        try:
            docs = self.vector_store.similarity_search(query, k=k)
            logger.debug(f"相似度搜索完成: query='{query}', 结果数={len(docs)}")
            return docs
        except Exception as e:
            logger.error(f"相似度搜索失败: {e}")
            return []

    # ── Partition operations (XHS RAG) ─────────────────────────────────

    def ensure_partition(self, kb_name: str, description: str = "") -> None:
        """幂等创建 partition。已存在则跳过。"""
        collection = milvus_manager.get_collection()
        if collection.has_partition(kb_name):
            logger.debug(f"partition '{kb_name}' 已存在")
            return
        collection.create_partition(
            partition_name=kb_name,
            description=description,
        )
        logger.info(f"创建 partition '{kb_name}', description='{description}'")

    def list_kb_partitions(self) -> List[dict]:
        """列出所有 xhs_ 前缀的 partition。

        Milvus 的 partition.description 在多个版本里不持久化（创建时设了、
        读回来却是空字符串）。这里做 metadata 回退：description 为空且
        partition 非空时，query 一条样本读 metadata.city 当 description。
        """
        collection = milvus_manager.get_collection()
        result: List[dict] = []
        for p in collection.partitions:
            if not p.name.startswith("xhs_"):
                continue
            desc = (getattr(p, "description", "") or "").strip()
            # Milvus partition description 不可靠时，回退到 metadata.city
            if not desc and p.num_entities > 0:
                try:
                    p.load()
                    sample = collection.query(
                        expr="id != ''",
                        output_fields=["metadata"],
                        partition_names=[p.name],
                        limit=1,
                    )
                    if sample:
                        md = sample[0].get("metadata") or {}
                        city = (md.get("city") or "").strip()
                        if city:
                            desc = city
                except Exception as e:
                    logger.warning(f"partition '{p.name}' description fallback 失败: {e}")
            result.append({
                "kb_name": p.name,
                "num_entities": p.num_entities,
                "description": desc,
            })
        return result

    def drop_kb_partition(self, kb_name: str) -> int:
        """删除 partition；不存在返回 -1，否则返回被删向量数。"""
        collection = milvus_manager.get_collection()
        if not collection.has_partition(kb_name):
            return -1
        partition = collection.partition(kb_name)
        n = partition.num_entities
        try:
            partition.release()
        except Exception as e:
            logger.warning(f"release partition '{kb_name}' 失败（可能未加载）: {e}")
        collection.drop_partition(kb_name)
        logger.info(f"删除 partition '{kb_name}', 释放 {n} 向量")
        return n

    def add_documents_to_partition(
        self, documents: List[Document], kb_name: str,
    ) -> List[str]:
        """入库到指定 partition。返回生成的 id 列表。"""
        if not documents:
            return []

        collection = milvus_manager.get_collection()
        if not collection.has_partition(kb_name):
            collection.create_partition(partition_name=kb_name)

        # 局部 import 让测试能 patch 这条模块路径
        from app.services.vector_embedding_service import vector_embedding_service as _emb

        texts = [d.page_content for d in documents]
        metadatas = [d.metadata or {} for d in documents]
        vectors = _emb.embed_documents(texts)
        ids = [str(uuid.uuid4()) for _ in documents]

        # 列式插入：与 milvus_client._create_collection 中的字段顺序一致
        # [id (VARCHAR), vector (FLOAT_VECTOR), content (VARCHAR), metadata (JSON)]
        collection.insert(
            data=[ids, vectors, texts, metadatas],
            partition_name=kb_name,
        )
        collection.flush()
        logger.info(f"partition '{kb_name}' 入库 {len(ids)} 向量")
        return ids

    def similarity_search_across_kb_partitions(
        self, query: str, k: int = 3,
    ) -> List[Document]:
        """跨所有 xhs_* partition 做向量检索（不污染 _default 等其他来源）。

        无 xhs_ partition 时返回空列表（不抛错）。
        """
        collection = milvus_manager.get_collection()
        kb_partitions = [p.name for p in collection.partitions if p.name.startswith("xhs_")]
        if not kb_partitions:
            return []

        # 每个 partition 都 load 一遍（已加载是 no-op）
        for name in kb_partitions:
            try:
                collection.partition(name).load()
            except Exception as e:
                logger.debug(f"partition '{name}' load: {e}")

        from app.services.vector_embedding_service import vector_embedding_service as _emb

        qv = _emb.embed_query(query)
        results = collection.search(
            data=[qv],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 16}},
            limit=k,
            partition_names=kb_partitions,
            output_fields=["content", "metadata"],
        )
        docs: List[Document] = []
        for hit in results[0]:
            docs.append(Document(
                page_content=hit.entity.get("content") or "",
                metadata=hit.entity.get("metadata") or {},
            ))
        logger.debug(
            f"跨 {len(kb_partitions)} 个 xhs_ partition 检索 query='{query[:30]}' 命中 {len(docs)}"
        )
        return docs

    def similarity_search_in_partition(
        self, query: str, kb_name: str, k: int = 3,
    ) -> List[Document]:
        """仅在指定 partition 内向量检索。"""
        collection = milvus_manager.get_collection()
        if not collection.has_partition(kb_name):
            raise KBNotFoundError(f"知识库 '{kb_name}' 不存在")

        # 新建 partition 默认未加载到内存，需主动 load（已加载时是 no-op）
        try:
            collection.partition(kb_name).load()
        except Exception as e:
            logger.debug(f"partition '{kb_name}' load: {e}")

        from app.services.vector_embedding_service import vector_embedding_service as _emb

        qv = _emb.embed_query(query)
        results = collection.search(
            data=[qv],
            anns_field="vector",
            param={"metric_type": "L2", "params": {"nprobe": 16}},
            limit=k,
            partition_names=[kb_name],
            output_fields=["content", "metadata"],
        )
        docs: List[Document] = []
        for hit in results[0]:
            docs.append(Document(
                page_content=hit.entity.get("content") or "",
                metadata=hit.entity.get("metadata") or {},
            ))
        logger.debug(f"partition '{kb_name}' 检索 query='{query[:30]}' 命中 {len(docs)}")
        return docs


# 全局单例
vector_store_manager = VectorStoreManager()
