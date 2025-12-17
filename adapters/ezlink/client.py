"""VectorAI适配器 - OpenAI兼容客户端"""
from openai import AsyncOpenAI
from config.settings import settings
from utils.logger import logger

class EzlinkAIAdapter(AsyncOpenAI):
    """VectorAI适配器 - 继承OpenAI客户端"""
    
    def __init__(self):
        # 初始化OpenAI客户端，但使用VectorAI的配置
        super().__init__(
            api_key=settings.external_service.ezlink_api_key or "",
            base_url=settings.external_service.ezlink_base_url,
            timeout=300.0
        )

# 创建全局实例
ezlink_client = EzlinkAIAdapter()