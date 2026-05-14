"""FastAPI 应用入口"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
import os

from app.config import config
from loguru import logger
from app.api import health, travel, chat, xhs, chat_rag


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=" * 60)
    logger.info(f"{config.app_name} v{config.app_version} 启动中...")
    logger.info(f"监听地址: http://{config.host}:{config.port}")
    logger.info(f"API 文档: http://{config.host}:{config.port}/docs")
    logger.info("=" * 60)
    from app.db.share_store import create_tables
    create_tables()
    logger.info("Share DB 初始化完成")
    yield
    logger.info(f"{config.app_name} 已关闭")


app = FastAPI(
    title=config.app_name,
    version=config.app_version,
    description="基于 LangChain 的旅游多智能体规划系统",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, tags=["健康检查"])
app.include_router(travel.router, prefix="/api", tags=["旅游规划"])
app.include_router(chat.router, prefix="/api", tags=["聊天"])
app.include_router(chat_rag.router, prefix="/api", tags=["RAG 对话"])
app.include_router(xhs.router, prefix="/api", tags=["小红书 RAG"])

static_dir = "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": f"Welcome to {config.app_name}", "docs": "/docs"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=config.host, port=config.port,
                reload=config.debug, log_level="info")
