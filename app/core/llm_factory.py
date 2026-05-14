"""LLM 工厂类

使用 LangChain ChatOpenAI 通过 OpenAI 兼容模式调用阿里云 DashScope
这种方式便于后续切换到其他支持 OpenAI API 的模型提供商

支持的模型提供商（只需修改 base_url 和 api_key）：
- 阿里云 DashScope: https://dashscope.aliyuncs.com/compatible-mode/v1
- OpenAI: https://api.openai.com/v1
- Azure OpenAI: https://{resource}.openai.azure.com
- 其他兼容 OpenAI API 的服务
"""

from langchain_openai import ChatOpenAI
from app.config import config
from loguru import logger


class LLMFactory:
    """LLM 工厂类 - 使用 OpenAI 兼容模式

    支持的模型提供商（修改 .env 即可切换）：
    - DeepSeek:         DEEPSEEK_API_KEY + DEEPSEEK_MODEL=deepseek-v4-pro
    - 阿里云 DashScope:  DASHSCOPE_API_KEY + RAG_MODEL=qwen-max
    - OpenAI:           修改 base_url 和 api_key
    """

    DASHSCOPE_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"

    @staticmethod
    def create_chat_model(
        model: str | None = None,
        temperature: float = 0.7,
        streaming: bool = True,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> ChatOpenAI:
        """通用聊天模型（RAG / 通用问答）"""
        model = model or config.dashscope_model
        base_url = base_url or LLMFactory.DASHSCOPE_BASE_URL
        api_key = api_key or config.dashscope_api_key

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
            extra_body={"stream": streaming},
        )

    @staticmethod
    def create_travel_llm(
        temperature: float = 0,
        streaming: bool = False,
        disable_thinking: bool = False,
    ) -> ChatOpenAI:
        """通用 LLM（旅游 Agent + 聊天）。

        优先使用 DeepSeek（DEEPSEEK_API_KEY 非空时），
        否则 fallback 到 DashScope（DASHSCOPE_API_KEY）。

        disable_thinking=True：禁用 DeepSeek thinking 模式（工具调用场景必须禁用，
        否则 reasoning_content 无法传回导致 400 错误）。
        """
        model    = config.travel_llm_model
        api_key  = config.travel_llm_api_key
        base_url = config.travel_llm_api_base

        logger.info("LLM 初始化: model={} base={} streaming={}", model, base_url.split("/")[2], streaming)

        extra: dict = {}
        is_deepseek = "deepseek" in (api_key or "").lower() or "deepseek.com" in (base_url or "")
        if is_deepseek and disable_thinking:
            extra["thinking"] = {"type": "disabled"}

        return ChatOpenAI(
            model=model,
            temperature=temperature,
            streaming=streaming,
            base_url=base_url,
            api_key=api_key,
            **({"extra_body": extra} if extra else {}),
        )


# 全局 LLM 工厂实例
llm_factory = LLMFactory()
