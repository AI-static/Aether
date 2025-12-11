"""图片生成路由"""
from sanic import Blueprint, Request
from sanic.response import json, HTTPResponse
from services.image_service import ImageService
from utils.logger import logger
from api.schema.image import CreateImageRequest, EditImageRequest, BatchCreateRequest
from api.schema.response import BaseResponse, ErrorCode, ErrorMessage

from pydantic import ValidationError

# 创建蓝图
bp = Blueprint("image", url_prefix="/image")

# 创建服务实例
image_service = ImageService()


@bp.post("/generate")
async def generate_image(request: Request):
    """生成图片"""
    try:
        data = CreateImageRequest(**request.json)
        logger.info(f"收到图片生成请求: {data.prompt[:50]}")
        
        result = await image_service.create_image(
            prompt=data.prompt,
            model=data.model,
            n=data.n,
            size=data.size,
            aspect_ratio=data.aspect_ratio,
            resolution=data.resolution
        )
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=ErrorMessage.IMAGE_GENERATE_SUCCESS if result["success"] else ErrorMessage.IMAGE_GENERATE_FAILED,
            data=result
        ).model_dump())
            
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except (ValueError, IndexError) as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": f"{e}"}
        ).model_dump(), status=400)


@bp.post("/edit")
async def edit_image(request: Request):
    """编辑图片"""
    try:
        # 检查是否有上传的图片文件
        if not request.files or not request.files.getlist('image'):
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message=ErrorMessage.PLEASE_SELECT_IMAGE
            ).model_dump(), status=400)
        
        # 获取上传的图片文件
        files = request.files.getlist('image')

        # 使用EditImageRequest验证参数
        data = EditImageRequest(
            prompt=request.form.get('prompt'),
            model=request.form.get('model'),
            n=int(request.form.get('n', 1)),
            size=request.form.get('size'),
            aspect_ratio=request.form.get('aspect_ratio'),
            resolution=request.form.get('resolution')
        )

        # 验证模型支持的参数
        from models.images import get_model_info
        model_info = get_model_info(data.model)
        if not model_info:
            raise ValueError(f"不支持的模型: {data.model}")
        
        # 验证并应用默认值
        aspect_ratio = data.aspect_ratio or '1:1'
        if model_info.supported_aspect_ratio and aspect_ratio not in model_info.supported_aspect_ratio:
            raise ValueError(f"不支持的长宽比: {aspect_ratio} 已支持的为 {model_info.supported_aspect_ratio}")
        
        resolution = data.resolution or "1K"
        if model_info.supported_resolution and resolution not in model_info.supported_resolution:
            raise ValueError(f"不支持的分辨率: {resolution} 已支持的为 {model_info.supported_resolution}")

        result = await image_service.edit_image(
            prompt=data.prompt,
            files=files,  # 直接传递files对象
            model=data.model,
            n=data.n,
            size=data.size,
            aspect_ratio=aspect_ratio,
            resolution=resolution
        )
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=ErrorMessage.IMAGE_EDIT_SUCCESS if result["success"] else ErrorMessage.IMAGE_EDIT_FAILED,
            data=result
        ).model_dump())
            
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except (ValueError, IndexError) as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": f"{e}"}
        ).model_dump(), status=400)


@bp.get("/models")
async def list_models(request: Request):
    """获取支持的模型列表"""
    models = await image_service.get_models()

    return json(BaseResponse(
        code=ErrorCode.SUCCESS,
        message=ErrorMessage.SUCCESS,
        data={
            "models": models
        }
    ).model_dump())


@bp.post("/upload")
async def upload_image(request: Request):
    """上传图片（图床功能）"""
    try:
        # 检查是否有上传的文件
        if not request.files:
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message=ErrorMessage.PLEASE_SELECT_IMAGE
            ).model_dump(), status=400)
        
        # 获取上传的文件
        files = request.files.get('image')
        if not files:
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message=ErrorMessage.PLEASE_SELECT_IMAGE
            ).model_dump(), status=400)
        
        # Sanic的files可能是列表或单个文件
        if isinstance(files, list):
            file = files[0]
        else:
            file = files
        
        filename = file.name
        image_data = file.body
        
        # 调用服务上传
        result = await image_service.upload_image(image_data, filename)
        
        if result["success"]:
            return json(BaseResponse(
                code=ErrorCode.SUCCESS,
                message=ErrorMessage.IMAGE_UPLOAD_SUCCESS,
                data=result
            ).model_dump())
        else:
            return json(BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message=result.get("error", ErrorMessage.IMAGE_UPLOAD_FAILED),
                data=None
            ).model_dump(), status=500)
            
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except (ValueError, IndexError) as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": f"{e}"}
        ).model_dump(), status=400)


@bp.post("/upload-url")
async def upload_from_url(request: Request):
    """从URL上传图片到图床"""
    try:
        data = request.json
        image_url = data.get("image_url")
        
        if not image_url:
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message=ErrorMessage.PROVIDE_IMAGE_URL
            ).model_dump(), status=400)
        
        # 调用服务上传
        result = await image_service.upload_from_url(image_url)
        
        if result["success"]:
            return json(BaseResponse(
                code=ErrorCode.SUCCESS,
                message=ErrorMessage.IMAGE_UPLOAD_SUCCESS,
                data=result
            ).model_dump())
        else:
            return json(BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message=result.get("error", ErrorMessage.IMAGE_UPLOAD_FAILED),
                data=None
            ).model_dump(), status=500)
            
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except (ValueError, IndexError) as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": f"{e}"}
        ).model_dump(), status=400)
