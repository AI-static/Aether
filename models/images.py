"""图片模型相关的Pydantic数据结构"""
from enum import Enum
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field


class ProviderEnum(str, Enum):
    """图片服务提供商枚举"""
    EZLINK = "Ezlink"
    VECTORAI = "VectorAI"


class ImageModel(BaseModel):
    """图片模型定义"""
    id: str = Field(..., description="模型ID")
    name: str = Field(..., description="模型名称")
    description: str = Field(..., description="模型描述")
    provider: ProviderEnum = Field(..., description="服务提供商")
    supported_sizes: Optional[List[str]] = Field(None, description="支持的尺寸")
    supported_aspect_ratio: Optional[List[str]] = Field(None, description="支持的长宽比")
    supported_resolution: Optional[List[str]] = Field(None, description="支持的分辨率")


# 模型注册表
IMAGE_MODELS: Dict[str, ImageModel] = {
    "gemini-2.5-flash-image-preview": ImageModel(
        id="gemini-2.5-flash-image-preview",
        name="Gemini 2.5 Flash Image Preview",
        description="Nano Banana 1.0 图片生成模型 (¥0.1/张)",
        provider=ProviderEnum.EZLINK,
        supported_sizes=["1024*1024", "1024*768", "768*1024", "512*512"]
    ),
    "gemini-3-pro-image-preview": ImageModel(
        id="gemini-3-pro-image-preview",
        name="Gemini 3 Pro Image Preview",
        description="Nano Banana 2.0 图片生成模型 (¥0.2/张)",
        provider=ProviderEnum.EZLINK,
        supported_aspect_ratio=["1:1","2:3","3:2","3:4","4:3","4:5","5:4","9:16","16:9","21:9"],
        supported_resolution=["1K", "2K", "4K"]
    ),
    "Z-Image-Turbo": ImageModel(
        id="Z-Image-Turbo",
        name="Z-Image-Turbo",
        description="阿里高速图片生成模型",
        provider=ProviderEnum.VECTORAI,
        supported_sizes=["1:1", "3:4", "4:3", "16:9"]
    )
}


def get_model_info(model_id: str) -> Optional[ImageModel]:
    """获取模型信息"""
    return IMAGE_MODELS.get(model_id)


def get_models_by_provider(provider: ProviderEnum) -> List[ImageModel]:
    """根据提供商获取模型列表"""
    return [model for model in IMAGE_MODELS.values() if model.provider == provider]


def get_all_models() -> List[ImageModel]:
    """获取所有模型列表"""
    return list(IMAGE_MODELS.values())