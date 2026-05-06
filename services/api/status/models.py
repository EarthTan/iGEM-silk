"""状态检查功能的数据模型"""

from pydantic import BaseModel


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str
    service: str
