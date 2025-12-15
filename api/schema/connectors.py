"""
简化的连接器配置类

只保留核心必要的配置，移除过度设计
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

__all__ = [
    "BaseConfig",
    "MonitorConfig",
    "ExtractConfig",
    "HarvestConfig",
    "PublishConfig",
    "ConfigFactory"
]


@dataclass
class BaseConfig:
    """基础配置"""
    session_id: Optional[str] = None
    timeout: int = 30


@dataclass
class MonitorConfig(BaseConfig):
    """监控配置"""
    urls: List[str]
    check_interval: int = 3600  # 1小时
    webhook_url: Optional[str] = None


@dataclass
class ExtractConfig(BaseConfig):
    """提取配置"""
    urls: List[str]
    schema: Optional[Dict[str, Any]] = None
    instruction: Optional[str] = None


@dataclass
class HarvestConfig(BaseConfig):
    """采收配置"""
    user_id: str = ""
    limit: Optional[int] = None
    content_types: List[str] = field(default_factory=lambda: ["posts"])


@dataclass
class PublishConfig(BaseConfig):
    """发布配置"""
    content: str = ""
    content_type: str = "text"  # text/image/video
    images: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


# 配置工厂
class ConfigFactory:
    """配置工厂，简化配置创建"""

    @staticmethod
    def monitor(urls: List[str], webhook_url: Optional[str] = None) -> MonitorConfig:
        """创建监控配置"""
        return MonitorConfig(urls=urls, webhook_url=webhook_url)

    @staticmethod
    def extract(urls: List[str], schema: Optional[Dict[str, Any]] = None) -> ExtractConfig:
        """创建提取配置"""
        return ExtractConfig(urls=urls, schema=schema)

    @staticmethod
    def harvest(user_id: str, limit: Optional[int] = None) -> HarvestConfig:
        """创建采收配置"""
        return HarvestConfig(user_id=user_id, limit=limit)

    @staticmethod
    def publish(
        content: str,
        content_type: str = "text",
        images: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> PublishConfig:
        """创建发布配置"""
        return PublishConfig(
            content=content,
            content_type=content_type,
            images=images or [],
            tags=tags or []
        )