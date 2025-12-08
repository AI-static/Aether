"""缓存工具"""
import redis
from typing import Any, Optional, Union
from config.settings import settings
from utils.logger import logger


class RedisClient:
    """Redis客户端"""
    
    def __init__(self):
        self.client = redis.Redis(
            host=settings.redis_host,
            port=settings.redis_port,
            db=settings.redis_db,
            password=settings.redis_password,
            decode_responses=True
        )
    
    def get(self, key: str) -> Optional[str]:
        """获取缓存值"""
        try:
            return self.client.get(key)
        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None
    
    def set(self, key: str, value: Any, expire: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            if isinstance(value, (dict, list)):
                import json
                value = json.dumps(value)
            return self.client.set(key, value, ex=expire)
        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            return bool(self.client.delete(key))
        except Exception as e:
            logger.error(f"Redis delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在"""
        try:
            return bool(self.client.exists(key))
        except Exception as e:
            logger.error(f"Redis exists error: {e}")
            return False
    
    def close(self):
        """关闭连接"""
        if self.client:
            self.client.close()


# 创建全局Redis实例
redis_client = RedisClient()