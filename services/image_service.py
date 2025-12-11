"""图片生成服务"""
from typing import List, Dict, Any, Optional
from adapters import ezlink_image_client, vectorai_client
from utils.logger import logger
from utils.exceptions import BusinessException
from api.schema.response import ErrorCode
from models.images import get_model_info, ProviderEnum
from config.settings import settings
from utils.oss import oss_client
from datetime import datetime
import hashlib


class ImageService:
    """图片生成业务服务"""
    
    def __init__(self):
        # OSS文件夹路径
        self.oss_folder = "Aether"

    async def create_image(self,
                           prompt: str,
                           model: str = "gemini-2.5-flash-image-preview",
                           n: int = 1,
                           size: str = "1024x1024",
                           aspect_ratio: str = '1:1',
                           resolution: str="1K") -> Dict[str, Any]:
        """
        创建图片
        :param prompt: 图片描述
        :param model: 模型名称
        :param n: 生成图片数量
        :param size: 图片尺寸
        :param aspect_ratio: 长宽比
        :param resolution: 分辨率
        :return: 包含图片链接和使用情况的结果
        """
        # 获取模型信息
        model_info = get_model_info(model)

        if not model_info:
            raise ValueError(f"不支持的模型: {model}")

        if size and size not in model_info.supported_sizes:
            raise ValueError(f"不支持的尺寸: {size} 已经支持的为 {model_info.supported_sizes}")

        if aspect_ratio and model_info.supported_aspect_ratio and aspect_ratio not in model_info.supported_aspect_ratio:
            raise ValueError(f"不支持的长宽比: {aspect_ratio} 已经支持的为 {model_info.supported_aspect_ratio}")

        if resolution and model_info.supported_resolution and resolution not in model_info.supported_resolution:
            raise ValueError(f"不支持的长宽比: {resolution} 已经支持的为 {model_info.supported_resolution}")

        logger.info(f"开始创建图片: {prompt[:100]} model_info {model_info}")

        # 根据提供商调用不同的API - 统一使用OpenAI格式
        if model_info.provider == ProviderEnum.VECTORAI:
            # 调用VectorAI (OpenAI兼容) API，使用url格式
            response = await vectorai_client.images.generate(
                prompt=prompt,
                model=model,
                n=n,
                size=size,
                extra_body = {
                    "watermark": True,
                },
            )
        else:
            # 调用Ezlink API (也返回OpenAI格式)，使用url格式
            response = await ezlink_image_client.generate_image(
                prompt, 
                model,
                size,
                aspect_ratio,
                resolution,
                response_format="url"
            )
        logger.info(f"生成图片service返回 {response}")
        if not response:
            provider_name = model_info.provider.value
            raise BusinessException(f"{provider_name} API 返回空结果", ErrorCode.IMAGE_GENERATE_FAILED)
        
        # 保存图片并生成URL
        images = await self._save_images_with_urls(response, model=model)

        # 构造返回结果
        result = {
            "success": True,
            "created": response.created,
            "images": images,
            "usage": {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.total_tokens
            },
            "prompt": prompt,
            "model": model,
            "size": size,
            "provider": model_info.provider.value
        }
        
        logger.info(f"图片生成成功，数量: {len(images)}，提供商: {model_info.provider.value}")
        return result
    
    async def edit_image(self, prompt: str, files,
                        model: str = "gemini-2.5-flash-image-preview", 
                        n: int = 1,
                        size: Optional[str] = None,
                        aspect_ratio: Optional[str] = None,
                        resolution: Optional[str] = None) -> Dict[str, Any]:
        """
        编辑图片
        :param prompt: 编辑描述
        :param files: 图片文件（可能是单个文件或文件列表）
        :param model: 模型名称
        :param n: 生成图片数量
        :param size: 图片尺寸
        :param aspect_ratio: 长宽比
        :param resolution: 分辨率
        :return: 编辑后的图片信息
        """
        logger.info(f"开始编辑图片: {prompt[:100]}")
        logger.info(f"files type: {type(files)}")
        
        # 调用Ezlink编辑API，一次性传入所有图片
        result = await ezlink_image_client.edit_image(prompt, files, model, n, size, aspect_ratio, resolution)
        
        if not result:
            raise BusinessException("Ezlink API 返回空结果", ErrorCode.IMAGE_EDIT_FAILED)
        
        # 保存图片并生成URL
        images = await self._save_images_with_urls(result, prefix="edited", model=model)
        
        # 构造返回结果
        response = {
            "success": True,
            "created": result.get("created"),
            "images": images,
            "usage": result.get("usage", {}),
            "prompt": prompt,
            "model": model,
            "size": size,
            "aspect_ratio": aspect_ratio,
            "resolution": resolution
        }
        
        logger.info(f"图片编辑成功，数量: {len(images)}")
        return response

    async def _save_images_with_urls(self, response, prefix: str = "generated", model: str = "unknown") -> List[Dict[str, Any]]:
        """
        保存图片并返回访问URL
        :param response: API返回结果（OpenAI格式对象）
        :param prefix: 文件名前缀
        :return: 包含URL的图片信息列表
        """
        if not response or not response.data:
            return []
            
        images = []

        for i, item in enumerate(response.data):
            # 直接使用adapter返回的URL（可能是外部URL或已上传到OSS的URL）
            if item.url:
                image_info = {
                    "index": i + 1,
                    "filename": f"{item.url.split('/')[-1]}" if item.url else f"{prefix}_{i+1}",
                    "url": item.url,
                    "path": None  # 不再需要path，因为文件都在OSS上
                }
                images.append(image_info)
                logger.info(f"图片URL: {item.url}")
            
            # 处理base64格式（直接返回，让上层处理）
            elif hasattr(item, 'b64_json') and item.b64_json:
                # 这里不应该出现，因为adapter已经处理了
                logger.warning("收到了未处理的base64数据，这不应该发生")
        
        return images
    
    async def batch_create_images(self, prompts: List[str], **kwargs) -> List[Dict[str, Any]]:
        """
        批量创建图片
        :param prompts: 图片描述列表
        :param kwargs: 其他参数（model, n, size等）
        :return: 所有图片的生成结果
        """
        results = []
        
        for i, prompt in enumerate(prompts):
            logger.info(f"批量生成图片进度: {i+1}/{len(prompts)}")
            result = await self.create_image(prompt, **kwargs)
            result["batch_index"] = i
            results.append(result)
            
        return results
    
    async def upload_image(self, image_data: bytes, filename: str = None) -> Dict[str, Any]:
        """
        上传图片到OSS（图床功能）
        :param image_data: 图片二进制数据
        :param filename: 文件名（可选）
        :return: 上传结果
        """
        logger.info(f"开始上传图片到OSS: {filename or '未命名'}")
        
        # 生成文件名
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            content_hash = hashlib.md5(image_data).hexdigest()[:8]
            filename = f"upload_{timestamp}_{content_hash}.png"
        
        # 确保文件有扩展名
        if not filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
            filename += '.png'
        
        try:
            # 上传到OSS
            object_name = f"{self.oss_folder}/{filename}"
            oss_url = await oss_client.upload_and_get_url(
                object_name, 
                image_data,
            )
            
            response = {
                "success": True,
                "filename": filename,
                "url": oss_url,
                "path": object_name,
                "size": len(image_data)
            }
            
            logger.info(f"图片上传到OSS成功: {filename}")
            return response
            
        except Exception as e:
            logger.error(f"图片上传到OSS失败: {e}")
            raise BusinessException(f"上传失败: {str(e)}", ErrorCode.IMAGE_UPLOAD_FAILED)
    
    
    async def get_models(self) -> List[Dict[str, Any]]:
        """获取所有支持的图片模型"""
        from models.images import get_all_models
        
        models = get_all_models()
        return [model.model_dump() for model in models]