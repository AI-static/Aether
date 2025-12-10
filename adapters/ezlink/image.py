"""Ezlink适配器 - OpenAI兼容包装器"""
import httpx
from typing import Dict, Any, Optional, List
from config.settings import settings
from utils.logger import logger
import base64
from datetime import datetime
from dataclasses import dataclass


# 定义OpenAI兼容的数据结构
@dataclass
class ImageData:
    b64_json: Optional[str] = None
    url: Optional[str] = None

@dataclass
class ImageUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0


@dataclass
class ImageResponse:
    created: int
    data: List[ImageData]
    usage: ImageUsage


class ImageAdapter:
    """Ezlink服务适配器 - OpenAI兼容"""
    
    def __init__(self):
        self.base_url = "https://api.ezlinkai.com/v1"  # Ezlink的固定base URL
        self.api_key = settings.ezlink_api_key
        self.timeout = 300  # 图片生成需要更长时间
        
    async def generate_image(self, prompt: str, model: str = "gemini-2.5-flash-image-preview", 
                            n: int = 1, size: str = "1024x1024", 
                            response_format: str = "b64_json") -> Optional[ImageResponse]:
        """
        创建图片 - 返回OpenAI兼容格式
        """
        if not self.api_key:
            logger.error("Ezlink API Key未配置")
            return None
            
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
                
                if response.status_code == 200:
                    ezlink_result = response.json()
                    
                    # 记录成功信息
                    logger.info(
                        f"[Ezlink] 生成图片成功 | "
                        f"状态码: {response.status_code} | "
                        f"模型: {model} | "
                        f"数量: {len(ezlink_result.get('data', []))}"
                        f"用量: {ezlink_result.get('usage', {})}"
                    )
                    
                    # 转换为OpenAI格式
                    image_data_list = []
                    for item in ezlink_result.get('data', []):
                        if response_format == "url":
                            # 如果是b64_json，需要先保存并返回URL
                            b64_data = item.get("b64_json")
                            if b64_data:
                                # 保存图片并生成URL
                                import os
                                import hashlib
                                from config.settings import settings
                                
                                os.makedirs(settings.image_dir, exist_ok=True)
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                content_hash = hashlib.md5(b64_data.encode()).hexdigest()[:8]
                                filename = f"{model}_{timestamp}_{content_hash}.png"
                                filepath = os.path.join(settings.image_dir, filename)
                                
                                # 解码并保存
                                image_bytes = base64.b64decode(b64_data)
                                with open(filepath, 'wb') as f:
                                    f.write(image_bytes)
                                
                                # 生成访问URL
                                image_url = f"/images/{filename}"
                                image_data_list.append(ImageData(url=image_url))
                        else:
                            # 返回b64_json
                            image_data_list.append(ImageData(b64_json=item.get("b64_json")))
                    
                    # 处理usage信息 - 兼容Ezlink格式
                    usage = ezlink_result.get("usage", {})
                    image_usage = ImageUsage(
                        input_tokens=usage.get("input_tokens", 0),
                        output_tokens=usage.get("output_tokens", 0),
                        total_tokens=usage.get("total_tokens", 0)
                    )
                    
                    return ImageResponse(
                        created=ezlink_result.get("created", int(datetime.now().timestamp())),
                        data=image_data_list,
                        usage=image_usage
                    )
                else:
                    logger.error(
                        f"[Ezlink] 生成图片失败 | "
                        f"状态码: {response.status_code} | "
                        f"错误: {response.text[:200]}"
                    )
                    return None
                    
        except httpx.TimeoutException as e:
            logger.error(f"调用Ezlink API超时: {e}")
            return None
        except httpx.RequestError as e:
            logger.error(f"调用Ezlink API请求错误: {e}")
            return None
        except Exception as e:
            logger.error(f"调用Ezlink API失败: {e}")
            return None


# 创建全局实例
ezlink_image_client = ImageAdapter()