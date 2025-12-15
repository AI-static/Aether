"""Ezlink适配器 - Gemini 风格的图片生成 API"""
from typing import Optional, List
from config.settings import settings
from utils.logger import logger
from utils.oss import oss_client
import base64
from datetime import datetime
import hashlib
import aiohttp
from openai import AsyncOpenAI
from dataclasses import dataclass


@dataclass
class ImagePart:
    """图片响应部分"""
    image_data: Optional[bytes] = None
    url: Optional[str] = None
    text: Optional[str] = None

    def as_image_bytes(self) -> Optional[bytes]:
        """获取图片字节数据"""
        return self.image_data

    def save(self, filename: str):
        """保存图片到文件"""
        if self.image_data:
            with open(filename, 'wb') as f:
                f.write(self.image_data)


@dataclass
class ImageResponse:
    """图片生成响应"""
    parts: List[ImagePart]
    created: int


class ImageConfig:
    """图片配置"""
    def __init__(self,
                 aspect_ratio: str = "1:1",
                 image_size: str = "1K",
                 size: Optional[str] = None):
        self.aspect_ratio = aspect_ratio
        self.image_size = image_size
        self.size = size


class GenerateContentConfig:
    """生成内容配置"""
    def __init__(self, image_config: Optional[ImageConfig] = None):
        self.image_config = image_config or ImageConfig()


class GeminiImageChat:
    """Gemini 风格的图片生成聊天接口"""

    def __init__(self, model: str, api_key: str, base_url: str):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.timeout = aiohttp.ClientTimeout(
            total=600,
            connect=30,
            sock_read=300
        )

    async def send_message(self,
                          message: str,
                          config: Optional[GenerateContentConfig] = None,
                          image_file: Optional[bytes] = None,
                          upload_to_oss: bool = True) -> ImageResponse:
        """
        发送消息生成图片 - Gemini 风格

        Args:
            message: 提示词或编辑指令
            config: 生成配置 (aspect_ratio, image_size)
            image_file: 可选的图片文件 (用于编辑)
            upload_to_oss: 是否上传到 OSS

        Returns:
            ImageResponse: 包含 parts 的响应
        """
        config = config or GenerateContentConfig()
        image_config = config.image_config

        try:
            if image_file:
                # 图片编辑模式
                return await self._edit_image(message, image_file, image_config, upload_to_oss)
            else:
                # 图片生成模式
                return await self._generate_image(message, image_config, upload_to_oss)

        except Exception as e:
            logger.error(f"[Gemini] 发送消息失败: {e}")
            raise

    async def _generate_image(self,
                             prompt: str,
                             image_config: ImageConfig,
                             upload_to_oss: bool) -> ImageResponse:
        """生成图片"""
        params = {
            "model": self.model,
            "prompt": prompt,
            "response_format": "b64_json"
        }

        # 添加图片配置
        if image_config.aspect_ratio:
            params["aspect_ratio"] = image_config.aspect_ratio
        if image_config.image_size:
            params["image_size"] = image_config.image_size
        if image_config.size:
            params["size"] = image_config.size

        logger.info(f"[Gemini] 生成图片 | 模型: {self.model} | 配置: {image_config.aspect_ratio}x{image_config.image_size}")

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                f"{self.base_url}/images/generations",
                json=params,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                }
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API 错误 {response.status}: {error_text[:200]}")

                result = await response.json()

                # 转换为 Gemini 风格的响应
                parts = []
                for item in result.get('data', []):
                    b64_data = item.get("b64_json")
                    if b64_data:
                        image_bytes = base64.b64decode(b64_data)

                        if upload_to_oss:
                            # 上传到 OSS
                            url = await self._upload_to_oss(image_bytes, self.model)
                            parts.append(ImagePart(image_data=image_bytes, url=url))
                        else:
                            parts.append(ImagePart(image_data=image_bytes))

                logger.info(f"[Gemini] 生成成功 | 数量: {len(parts)}")

                return ImageResponse(
                    parts=parts,
                    created=result.get("created", int(datetime.now().timestamp()))
                )

    async def _edit_image(self,
                         prompt: str,
                         image_file: bytes,
                         image_config: ImageConfig,
                         upload_to_oss: bool) -> ImageResponse:
        """编辑图片"""
        logger.info(f"[Gemini] 编辑图片 | 模型: {self.model}")

        # 准备 multipart/form-data
        data = aiohttp.FormData()
        data.add_field('prompt', prompt)
        data.add_field('model', self.model)

        if image_config.aspect_ratio:
            data.add_field('aspect_ratio', image_config.aspect_ratio)
        if image_config.image_size:
            data.add_field('image_size', image_config.image_size)
        if image_config.size:
            data.add_field('size', image_config.size)

        # 添加图片
        data.add_field(
            'image',
            image_file,
            filename='image.png',
            content_type='image/png'
        )

        async with aiohttp.ClientSession(timeout=self.timeout) as session:
            async with session.post(
                f"{self.base_url}/images/generations",
                data=data,
                headers={"Authorization": f"Bearer {self.api_key}"}
            ) as response:
                if response.status != 200:
                    error_text = await response.text()
                    raise Exception(f"API 错误 {response.status}: {error_text[:200]}")

                result = await response.json()

                # 转换为 Gemini 风格的响应
                parts = []
                for item in result.get('data', []):
                    b64_data = item.get("b64_json")
                    if b64_data:
                        image_bytes = base64.b64decode(b64_data)

                        if upload_to_oss:
                            url = await self._upload_to_oss(image_bytes, f"{self.model}_edit")
                            parts.append(ImagePart(image_data=image_bytes, url=url))
                        else:
                            parts.append(ImagePart(image_data=image_bytes))

                logger.info(f"[Gemini] 编辑成功 | 数量: {len(parts)}")

                return ImageResponse(
                    parts=parts,
                    created=result.get("created", int(datetime.now().timestamp()))
                )

    async def _upload_to_oss(self, image_bytes: bytes, prefix: str) -> str:
        """上传图片到 OSS"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.md5(image_bytes).hexdigest()[:8]
        filename = f"gemini_{prefix}_{timestamp}_{content_hash}.png"
        object_name = f"Aether/{filename}"

        url = await oss_client.upload_and_get_url(object_name, image_bytes)
        logger.debug(f"[Gemini] 已上传 OSS: {url}")
        return url


class ImageAdapter(AsyncOpenAI):
    """Ezlink 图片适配器 - Gemini 风格接口"""

    def __init__(self):
        self.api_key = settings.ezlink_api_key
        self.base_url = settings.ezlink_base_url

        if not self.api_key:
            raise ValueError("EZLINK_API_KEY 未配置")

    async def _upload_to_oss(self, image_bytes: bytes, prefix: str) -> str:
        """上传图片到 OSS"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        content_hash = hashlib.md5(image_bytes).hexdigest()[:8]
        filename = f"gemini_{prefix}_{timestamp}_{content_hash}.png"
        object_name = f"Aether/{filename}"

        url = await oss_client.upload_and_get_url(object_name, image_bytes)
        logger.debug(f"[Gemini] 已上传 OSS: {url}")
        return url


    async def generate_image(self,
                            prompt: str,
                            model: str,
                            size: Optional[str] = None,
                            aspect_ratio: Optional[str] = None,
                            resolution: Optional[str] = None,
                            response_format: str = "url") -> dict:
        """
        生成图片 - OpenAI 兼容接口

        Args:
            prompt: 图片描述
            model: 模型名称
            size: 图片尺寸（如 "1024x1024"）
            aspect_ratio: 长宽比（如 "1:1"）
            resolution: 分辨率（如 "1K"）
            response_format: 返回格式 ("url" 或 "b64_json")

        Returns:
            OpenAI 格式的响应字典
        """
        # 创建配置
        image_config = ImageConfig(
            aspect_ratio=aspect_ratio or "1:1",
            image_size=resolution or "1K",
            size=size
        )

        config = GenerateContentConfig(image_config=image_config)

        # 创建聊天会话并生成图片
        upload_to_oss = (response_format == "url")

        response = await self.chat.send_message(
            prompt,
            config=config,
            upload_to_oss=upload_to_oss
        )

        # 转换为 OpenAI 格式
        data = []
        for part in response.parts:
            if response_format == "url" and part.url:
                data.append({"url": part.url})
            elif response_format == "b64_json" and part.image_data:
                b64_data = base64.b64encode(part.image_data).decode('utf-8')
                data.append({"b64_json": b64_data})

        return {
            "created": response.created,
            "data": data
        }


# 创建全局实例
ezlink_image_client = ImageAdapter()
