"""配置模型"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ConfigType(str, Enum):
    """配置类型"""
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"
    LIST = "list"


class ConfigStatus(str, Enum):
    """配置状态"""
    ACTIVE = "active"
    INACTIVE = "inactive"
    DELETED = "deleted"


class ConfigCategory(str, Enum):
    """配置分类"""
    SYSTEM = "system"  # 系统配置
    BUSINESS = "business"  # 业务配置
    THIRD_PARTY = "third_party"  # 第三方配置


# 请求模型
class ConfigTypeCreateRequest(BaseModel):
    """创建配置类型"""
    type_code: str = Field(..., description="配置类型代码")
    type_name: str = Field(..., description="配置类型名称")
    category: ConfigCategory = Field(..., description="配置分类")
    description: Optional[str] = Field(None, description="描述")
    schema_definition: Optional[Dict[str, Any]] = Field(None, description="结构定义")


class ConfigDataCreateRequest(BaseModel):
    """创建配置数据"""
    type_code: str = Field(..., description="配置类型代码")
    key: str = Field(..., description="配置键名")
    name: str = Field(..., description="配置名称")
    value: Dict[str, Any] = Field(..., description="配置值")
    description: Optional[str] = Field(None, description="描述")
    tags: Optional[List[str]] = Field(None, description="标签")


class ConfigDataUpdateRequest(BaseModel):
    """更新配置数据"""
    value: Dict[str, Any] = Field(..., description="配置值")
    name: Optional[str] = Field(None, description="配置名称")
    description: Optional[str] = Field(None, description="描述")
    tags: Optional[List[str]] = Field(None, description="标签")


class ConfigQueryRequest(BaseModel):
    """查询配置"""
    type_code: Optional[str] = Field(None, description="配置类型代码")
    key: Optional[str] = Field(None, description="配置键")
    tags: Optional[List[str]] = Field(None, description="标签")
    status: Optional[ConfigStatus] = Field(None, description="状态")
    page: int = Field(1, ge=1, description="页码")
    page_size: int = Field(20, ge=1, le=100, description="每页大小")


class ConfigGetRequest(BaseModel):
    """获取配置"""
    key: Optional[str] = Field(None, description="配置键")
    type_code: Optional[str] = Field(None, description="配置类型代码")


# 响应模型
class ConfigTypeResponse(BaseModel):
    """配置类型响应"""
    id: int
    type_code: str
    type_name: str
    category: ConfigCategory
    description: Optional[str]
    schema_definition: Optional[Dict]
    create_time: datetime
    
    class Config:
        from_attributes = True


class ConfigDataResponse(BaseModel):
    """配置数据响应"""
    id: int
    type_code: str
    key: str
    name: str
    value: Dict[str, Any]
    description: Optional[str]
    tags: Optional[List[str]]
    status: ConfigStatus
    create_time: datetime
    update_time: Optional[datetime]
    
    class Config:
        from_attributes = True