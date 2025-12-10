from pydantic import BaseModel, Field, field_serializer
from typing import Optional
from datetime import datetime
from enum import Enum


class SourceType(str, Enum):
    """来源类型枚举"""
    SYSTEM = "system"  # 系统管理员，可以管理所有密钥
    SERVICE = "service"  # 服务间调用
    USER = "user"  # 普通用户
    APP = "app"  # 应用程序


# 自定义 Pydantic 模型用于API请求/响应
class ApiKeyCreate(BaseModel):
    """创建API密钥请求"""
    source: Optional[SourceType] = Field(SourceType.USER, description="来源类型")
    source_id: Optional[str] = Field(None, description="来源ID")
    name: Optional[str] = Field(None, description="密钥名称")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    usage_limit: Optional[int] = Field(None, description="使用次数限制")


class ApiKeyResponse(BaseModel):
    """API密钥响应"""
    id: str
    source: SourceType
    source_id: str
    api_key: str  # 只在创建时返回完整密钥
    name: Optional[str]
    expires_at: Optional[datetime]
    usage_limit: Optional[int]
    usage_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at', 'expires_at', when_used='always')
    def serialize_dt(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()

    class Config:
        from_attributes = True


class ApiKeyInfo(BaseModel):
    """API密钥信息（不包含完整密钥）"""
    id: str
    source: SourceType
    source_id: str
    name: Optional[str]
    expires_at: Optional[datetime]
    usage_limit: Optional[int]
    usage_count: int
    is_active: bool
    created_at: datetime
    updated_at: datetime

    @field_serializer('created_at', 'updated_at', 'expires_at', when_used='always')
    def serialize_dt(self, value: Optional[datetime]) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat()

    class Config:
        from_attributes = True


class ApiKeyUpdate(BaseModel):
    """更新API密钥请求"""
    name: Optional[str] = None
    expires_at: Optional[datetime] = None
    usage_limit: Optional[int] = None
    is_active: Optional[bool] = None
