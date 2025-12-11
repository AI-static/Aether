"""Ezlink适配器 - OpenAI兼容包装器"""
import aiohttp
from typing import Dict, Any, Optional, List
from config.settings import settings
from utils.logger import logger
from utils.oss import oss_client
import base64
from datetime import datetime
from dataclasses import dataclass
import hashlib
import asyncio


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
        self.base_url = settings.ezlink_base_url
        self.api_key = settings.ezlink_api_key
        self.timeout = aiohttp.ClientTimeout(
            total=600,  # 总超时时间增加到10分钟
            connect=30,  # 连接超时30秒
            sock_read=300  # 读取超时5分钟
        )

    async def generate_image(self,
                             prompt: str,
                             model: str = "gemini-2.5-flash-image-preview",
                             size: str = None,
                             aspect_ratio: str = None,
                             resolution: str = None,
                             response_format: str = "b64_json") -> Optional[ImageResponse]:
        """
        创建图片 - 返回OpenAI兼容格式
        """
        if not self.api_key:
            logger.error("Ezlink API Key未配置")
            return None

        try:
            params = {
                        "model": model,
                        "prompt": prompt,
                    }
            if size:
                params.update({'size': size})
            if aspect_ratio:
                params.update({'aspect_ratio': aspect_ratio})
            if resolution:
                params.update({'image_size': resolution})

            logger.info(f"[Ezlink] 开始生成图片 | 模型: {model} | params: {params}")
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/images/generations",
                    json=params,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    }
                ) as response:
                    if response.status == 200:
                        ezlink_result = await response.json()
                        
                        # 记录成功信息
                        logger.info(
                            f"[Ezlink] 生成图片成功 | "
                            f"状态码: {response.status} | "
                            f"模型: {model} | "
                            f"数量: {len(ezlink_result.get('data', []))}"
                            f"用量: {ezlink_result.get('usage', {})}"
                        )
                        
                        # 转换为OpenAI格式
                        image_data_list = []
                        for item in ezlink_result.get('data', []):
                            if response_format == "url":
                                # 如果是b64_json，上传到OSS并返回URL
                                b64_data = item.get("b64_json")
                                if b64_data:
                                    # 解码图片
                                    image_bytes = base64.b64decode(b64_data)
                                    
                                    # 生成文件名
                                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    content_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                                    filename = f"ezlink_{model}_{timestamp}_{content_hash}.png"
                                    
                                    # 上传到OSS
                                    object_name = f"Aether/{filename}"
                                    oss_url = await oss_client.upload_and_get_url(
                                        object_name,
                                        image_bytes,
                                    )
                                    
                                    image_data_list.append(ImageData(url=oss_url))
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
                        error_text = await response.text()
                        logger.error(
                            f"[Ezlink] 生成图片失败 | "
                            f"状态码: {response.status} | "
                            f"错误: {error_text[:200]}"
                        )
                        return None
                    
        except asyncio.TimeoutError as e:
            logger.error(f"调用Ezlink API超时: {e}")
            return None
        except asyncio.CancelledError as e:
            logger.error(f"调用Ezlink API被取消: {e}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"调用Ezlink API请求错误: {e}")
            return None
        except Exception as e:
            logger.error(f"调用Ezlink API失败: {e}")
            return None

    async def edit_image(self,
                        prompt: str,
                        files,
                        model: str = "gemini-2.5-flash-image-preview",
                        n: int = 1,
                        size: Optional[str] = None,
                        aspect_ratio: Optional[str] = None,
                        resolution: Optional[str] = None) -> Optional[ImageResponse]:
        """
        编辑图片 - 返回OpenAI兼容格式
        """
        if not self.api_key:
            logger.error("Ezlink API Key未配置")
            return None

        try:
            logger.info(f"[Ezlink] 开始编辑图片 | 模型: {model} | 提示: {prompt[:50]}...")
            
            # 准备multipart/form-data
            data = aiohttp.FormData()
            data.add_field('prompt', prompt)
            data.add_field('model', model)
            data.add_field('n', str(n))
            
            if size:
                data.add_field('size', size)
            if aspect_ratio:
                data.add_field('aspect_ratio', aspect_ratio)
            if resolution:
                data.add_field('resolution', resolution)
            
            # 添加图片文件
            for file in files:
                data.add_field(
                    'image',
                    file.body,
                    filename=file.name,
                    content_type='image/jpeg'
                )
            
            async with aiohttp.ClientSession(timeout=self.timeout) as session:
                async with session.post(
                    f"{self.base_url}/images/generations",
                    data=data,
                    headers={
                        "Authorization": f"Bearer {self.api_key}"
                    }
                ) as response:
                    if response.status == 200:
                        ezlink_result = await response.json()
                        
                        # 记录成功信息
                        logger.info(
                            f"[Ezlink] 编辑图片成功 | "
                            f"状态码: {response.status} | "
                            f"模型: {model} | "
                            f"数量: {len(ezlink_result.get('data', []))}"
                            f"用量: {ezlink_result.get('usage', {})}"
                        )
                        
                        # 转换为OpenAI格式
                        image_data_list = []
                        for item in ezlink_result.get('data', []):
                            # 如果是b64_json，上传到OSS并返回URL
                            b64_data = item.get("b64_json")
                            if b64_data:
                                # 解码图片
                                image_bytes = base64.b64decode(b64_data)
                                
                                # 生成文件名
                                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                                content_hash = hashlib.md5(image_bytes).hexdigest()[:8]
                                filename = f"ezlink_edit_{model}_{timestamp}_{content_hash}.png"
                                
                                # 上传到OSS
                                object_name = f"Aether/{filename}"
                                oss_url = await oss_client.upload_and_get_url(
                                    object_name,
                                    image_bytes,
                                )
                                
                                image_data_list.append(ImageData(url=oss_url))
                            else:
                                # 直接使用返回的URL
                                url = item.get("url")
                                if url:
                                    image_data_list.append(ImageData(url=url))
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
                        error_text = await response.text()
                        logger.error(
                            f"[Ezlink] 编辑图片失败 | "
                            f"状态码: {response.status} | "
                            f"错误: {error_text[:200]}"
                        )
                        return None
                    
        except asyncio.TimeoutError as e:
            logger.error(f"调用Ezlink API超时: {e}")
            return None
        except asyncio.CancelledError as e:
            logger.error(f"调用Ezlink API被取消: {e}")
            return None
        except aiohttp.ClientError as e:
            logger.error(f"调用Ezlink API请求错误: {e}")
            return None
        except Exception as e:
            logger.error(f"调用Ezlink API失败: {e}")
            return None


# 创建全局实例
ezlink_image_client = ImageAdapter()