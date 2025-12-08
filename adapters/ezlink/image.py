"""Ezlink适配器"""
import httpx
from typing import Dict, Any, Optional, List
from config.settings import settings
from utils.logger import logger
from utils.cache import redis_client
import base64


class EzlinkAdapter:
    """Ezlink服务适配器"""
    
    def __init__(self):
        self.base_url = "https://api.ezlinkai.com/v1"
        self.api_key = settings.ezlink_api_key
        self.timeout = 60  # 图片生成需要更长时间
        
    async def generate_image(self, prompt: str, model: str = "gemini-2.5-flash-image-preview", 
                            n: int = 1, size: str = "1024x1024") -> Optional[Dict]:
        """
        创建图片
        返回格式：
        {
            "created": 时间戳,
            "data": [{"b64_json": "base64编码的图片"}],
            "usage": {
                "total_tokens": 总token数,
                "input_tokens": 输入token数,
                "output_tokens": 输出token数,
                "input_tokens_details": {
                    "text_tokens": 文本token数,
                    "image_tokens": 图片token数
                }
            }
        }
        """
        if not self.api_key:
            logger.error("Ezlink API Key未配置")
            return None
            
        # 检查缓存
        cache_key = f"ezlink:generate:{hash(prompt)}:{model}:{n}:{size}"
        cached_result = redis_client.get(cache_key)
        if cached_result:
            logger.info(f"从缓存获取图片生成结果: {prompt[:50]}")
            return cached_result
            
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/images/generations",
                    json={
                        "model": model,
                        "prompt": prompt,
                        "n": n,
                        "size": size
                    },
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                )
                logger.info(f"[Ezlink] 图片生成返回: {response}")

                if response.status_code == 200:
                    result = response.json()
                    
                    # 缓存结果（24小时）
                    redis_client.set(cache_key, result, expire=86400)
                    
                    logger.info(f"图片生成成功: {prompt[:50]}")
                    return result
                else:
                    logger.error(f"图片生成失败: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"调用Ezlink API失败: {e}")
            return None
    
    async def edit_image(self, prompt: str, image_data: bytes, 
                        model: str = "gemini-2.5-flash-image-preview", 
                        n: int = 4) -> Optional[Dict]:
        """
        编辑图片
        :param prompt: 编辑描述
        :param image_data: 图片二进制数据
        :param model: 模型名称
        :param n: 生成图片数量
        :return: 生成的图片数据
        """
        if not self.api_key:
            logger.error("Ezlink API Key未配置")
            return None
            
        try:
            # 将图片数据转换为bytes
            files = {
                'model': (None, model),
                'prompt': (None, prompt),
                'n': (None, str(n)),
                'image': ('image.jpg', image_data, 'image/jpeg')
            }
            
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(
                    f"{self.base_url}/images/generations",
                    files=files,
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    }
                )
                
                if response.status_code == 200:
                    result = response.json()
                    logger.info(f"图片编辑成功: {prompt[:50]}")
                    return result
                else:
                    logger.error(f"图片编辑失败: {response.status_code} - {response.text}")
                    return None
                    
        except Exception as e:
            logger.error(f"编辑图片失败: {e}")
            return None
    
    async def save_generated_images(self, result: Dict, output_dir: str = "generated_images") -> List[str]:
        """
        保存生成的图片到文件
        :param result: generate_image或edit_image的返回结果
        :param output_dir: 输出目录
        :return: 保存的文件路径列表
        """
        import os
        from datetime import datetime
        
        if not result or 'data' not in result:
            return []
            
        # 创建输出目录
        os.makedirs(output_dir, exist_ok=True)
        
        saved_files = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        for i, item in enumerate(result['data']):
            if 'b64_json' in item:
                # 解码base64图片
                image_data = base64.b64decode(item['b64_json'])
                
                # 生成文件名
                filename = f"ezlink_{timestamp}_{i+1}.png"
                filepath = os.path.join(output_dir, filename)
                
                # 保存文件
                with open(filepath, 'wb') as f:
                    f.write(image_data)
                    
                saved_files.append(filepath)
                logger.info(f"保存图片: {filepath}")
                
        return saved_files
    
    async def get_image_from_url(self, image_url: str) -> Optional[bytes]:
        """
        从URL下载图片
        :param image_url: 图片URL
        :return: 图片二进制数据
        """
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.get(image_url)
                if response.status_code == 200:
                    return response.content
                else:
                    logger.error(f"下载图片失败: {response.status_code}")
                    return None
        except Exception as e:
            logger.error(f"下载图片失败: {e}")
            return None