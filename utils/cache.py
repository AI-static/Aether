"""简单缓存实现 - 基于内存"""

import time
import threading
from typing import Any, Optional, Dict
from utils.logger import logger


class MemoryCache:
    """简单的内存缓存实现"""
    
    def __init__(self, default_ttl: int = 300):  # 默认5分钟过期
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.lock = threading.RLock()
        self.default_ttl = default_ttl
    
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        try:
            with self.lock:
                if key not in self.cache:
                    return None
                
                item = self.cache[key]
                
                # 检查是否过期
                if item['expire_at'] and time.time() > item['expire_at']:
                    del self.cache[key]
                    return None
                
                return item['value']
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """设置缓存值"""
        try:
            with self.lock:
                expire_at = None
                if ttl is not None:
                    expire_at = time.time() + ttl
                elif self.default_ttl > 0:
                    expire_at = time.time() + self.default_ttl
                
                self.cache[key] = {
                    'value': value,
                    'expire_at': expire_at,
                    'created_at': time.time()
                }
                return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False
    
    def delete(self, key: str) -> bool:
        """删除缓存"""
        try:
            with self.lock:
                if key in self.cache:
                    del self.cache[key]
                    return True
                return False
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """检查键是否存在且未过期"""
        return self.get(key) is not None
    
    def clear(self):
        """清空所有缓存"""
        try:
            with self.lock:
                self.cache.clear()
                return True
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return False


# 创建全局缓存实例
cache = MemoryCache(default_ttl=300)  # 5分钟默认TTL