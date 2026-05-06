"""工具查询功能的数据模型"""

from pydantic import BaseModel


class ToolInfo(BaseModel):
    """工具信息。"""
    name: str
    url: str
    type: str
    priority: int
    requires_gpu: bool


class ToolListResponse(BaseModel):
    """工具列表响应。"""
    tools: list[ToolInfo]
