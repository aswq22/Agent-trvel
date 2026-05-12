"""健康检查接口"""

from fastapi import APIRouter
from app.config import config

router = APIRouter()


@router.get("/health")
async def health_check():
    """服务健康检查"""
    return {
        "code": 200,
        "message": "服务运行正常",
        "data": {
            "service": config.app_name,
            "version": config.app_version,
            "status": "healthy",
        },
    }
