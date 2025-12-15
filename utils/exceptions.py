"""自定义异常类"""
from typing import Optional
from api.schema.base import ErrorCode


class BusinessException(Exception):
    """业务异常基类"""
    def __init__(self, message: str, code: int = ErrorCode.INTERNAL_ERROR, details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(self.message)