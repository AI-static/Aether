"""API基础响应模型"""
from pydantic import BaseModel
from typing import Any, Optional


class BaseResponse(BaseModel):
    """基础响应"""
    code: int = 0
    message: str = "success"
    data: Optional[Any] = None


class PageResponse(BaseModel):
    """分页响应"""
    items: list
    total: int
    page: int
    page_size: int
    total_pages: int
