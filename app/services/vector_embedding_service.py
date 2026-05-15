"""向量嵌入服务模块 - 本地 sentence-transformers 实现 LangChain Embeddings 接口

默认模型 BAAI/bge-small-zh-v1.5：512 维、~100MB、中文质量好、CPU 推理够快。
首次启动会从 HuggingFace 下载模型到 ~/.cache/huggingface。
"""

from typing import List

from langchain_core.embeddings import Embeddings
from loguru import logger


class LocalEmbeddings(Embeddings):
    """本地 sentence-transformers 嵌入服务。

    实现 LangChain 标准 Embeddings 接口:
    - embed_documents(texts: List[str]) -> List[List[float]]
    - embed_query(text: str) -> List[float]
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-small-zh-v1.5",
        dimensions: int = 512,
        normalize: bool = True,
    ):
        """
        Args:
            model_name: HuggingFace 模型仓库名
            dimensions: 输出向量维度（用于校验，模型本身决定真实维度）
            normalize: 是否做 L2 归一化（bge 系列推荐 True）
        """
        # 延迟 import：避免在不需要 embedding 的子流程里强制加载 torch
        from sentence_transformers import SentenceTransformer

        logger.info(f"加载本地 embedding 模型: {model_name} ...")
        self._model = SentenceTransformer(model_name)
        self.model_name = model_name
        self.dimensions = dimensions
        self.normalize = normalize
        actual_dim = self._model.get_sentence_embedding_dimension()
        logger.info(
            f"本地 Embeddings 初始化完成 — 模型: {model_name}, "
            f"维度: {actual_dim} (配置 {dimensions}), normalize={normalize}"
        )
        if actual_dim != dimensions:
            logger.warning(
                f"⚠ 模型实际维度 {actual_dim} 与配置 {dimensions} 不一致，"
                "请同步更新 milvus_client.VECTOR_DIM"
            )

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """批量嵌入文档列表 (LangChain 标准接口)"""
        if not texts:
            return []
        try:
            logger.info(f"批量嵌入 {len(texts)} 个文档")
            vectors = self._model.encode(
                texts,
                normalize_embeddings=self.normalize,
                show_progress_bar=False,
            )
            # SentenceTransformer.encode 返回 ndarray；转 list[list[float]]
            return [v.tolist() for v in vectors]
        except Exception as e:
            logger.error(f"批量嵌入失败: {e}")
            raise RuntimeError(f"批量嵌入失败: {e}") from e

    def embed_query(self, text: str) -> List[float]:
        """嵌入单个查询文本 (LangChain 标准接口)"""
        if not text or not text.strip():
            raise ValueError("查询文本不能为空")
        try:
            vector = self._model.encode(
                text,
                normalize_embeddings=self.normalize,
                show_progress_bar=False,
            )
            return vector.tolist()
        except Exception as e:
            logger.error(f"查询嵌入失败: {e}")
            raise RuntimeError(f"查询嵌入失败: {e}") from e


# 全局单例
vector_embedding_service = LocalEmbeddings(
    model_name="BAAI/bge-small-zh-v1.5",
    dimensions=512,
    normalize=True,
)
