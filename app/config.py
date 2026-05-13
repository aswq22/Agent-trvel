"""配置管理模块

使用 Pydantic Settings 实现类型安全的配置管理
"""

from typing import Dict, Any
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """应用配置"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # 应用配置
    app_name: str = "SuperBizAgent"
    app_version: str = "1.0.0"
    debug: bool = False
    host: str = "0.0.0.0"
    port: int = 9900

    # DashScope 配置
    dashscope_api_key: str = ""
    dashscope_api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_model: str = "qwen-max"
    dashscope_embedding_model: str = "text-embedding-v4"

    # Milvus 配置
    milvus_host: str = "localhost"
    milvus_port: int = 19530
    milvus_timeout: int = 10000  # 毫秒

    # RAG 配置
    rag_top_k: int = 3
    rag_model: str = "qwen-max"  # 使用快速响应模型，不带扩展思考

    # 文档分块配置
    chunk_max_size: int = 800
    chunk_overlap: int = 100

    # MCP 服务配置
    mcp_cls_transport: str = "streamable-http"
    mcp_cls_url: str = "http://localhost:8003/mcp"
    mcp_monitor_transport: str = "streamable-http"
    mcp_monitor_url: str = "http://localhost:8004/mcp"

    # Gaode Maps API
    gaode_api_key: str = ""
    # 高德地图 JS API Key（用于前端地图展示）
    amap_js_key: str = ""
    # 分享链接数据库 URL
    share_db_url: str = "sqlite:///data/shares.db"

    # 美团开放平台（企业资质，申请：https://open.meituan.com）
    meituan_app_key: str = ""
    meituan_app_secret: str = ""

    # Travel MCP server URLs
    mcp_gaode_url: str = "http://localhost:8010/mcp"
    mcp_ctrip_url: str = "http://localhost:8011/mcp"
    mcp_dianping_url: str = "http://localhost:8012/mcp"

    @property
    def mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        """获取完整的 MCP 服务器配置"""
        return {
            "cls": {
                "transport": self.mcp_cls_transport,
                "url": self.mcp_cls_url,
            },
            "monitor": {
                "transport": self.mcp_monitor_transport,
                "url": self.mcp_monitor_url,
            }
        }

    @property
    def travel_mcp_servers(self) -> Dict[str, Dict[str, Any]]:
        """获取旅游相关的 MCP 服务器配置"""
        return {
            "gaode": {"transport": "streamable-http", "url": self.mcp_gaode_url},
            "ctrip": {"transport": "streamable-http", "url": self.mcp_ctrip_url},
            "dianping": {"transport": "streamable-http", "url": self.mcp_dianping_url},
        }


# 全局配置实例
config = Settings()
