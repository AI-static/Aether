"""配置路由"""
from sanic import Blueprint, Request
from sanic.response import json, HTTPResponse
from services.config_service import ConfigService
from models.config import (
    ConfigTypeCreateRequest, ConfigDataCreateRequest,
    ConfigDataUpdateRequest, ConfigQueryRequest, ConfigGetRequest
)

from api.schema.base import PageResponse
from api.schema.response import BaseResponse, ErrorCode, ErrorMessage
from utils.logger import logger
from pydantic import ValidationError

# 创建蓝图
bp = Blueprint("config", url_prefix="/config")

# 创建服务实例
config_service = ConfigService()


@bp.post("/types")
async def create_config_type(request: Request):
    """创建配置类型"""
    try:
        data = ConfigTypeCreateRequest(**request.json)
        result = await config_service.create_config_type(data)
        return json(BaseResponse(data=result.model_dump()).model_dump())
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"创建配置类型失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR
        ).model_dump(), status=500)


@bp.post("")
async def create_config(request: Request):
    """创建配置"""
    try:
        data = ConfigDataCreateRequest(**request.json)
        result = await config_service.create_config(data)
        return json(BaseResponse(data=result.model_dump()).model_dump())
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"创建配置失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR
        ).model_dump(), status=500)