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


@bp.get("")
async def get_config(request: Request):
    """获取配置"""
    try:
        query = ConfigGetRequest(**request.args)
        result = await config_service.get_config(query)
        if result:
            return json(BaseResponse(data=result.model_dump()).model_dump())
        else:
            return json(BaseResponse(
                code=ErrorCode.NOT_FOUND,
                message=ErrorMessage.NOT_FOUND
            ).model_dump(), status=404)
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"获取配置失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR
        ).model_dump(), status=500)


@bp.get("/list")
async def list_configs(request: Request):
    """查询配置列表"""
    try:
        query = ConfigQueryRequest(**request.args)
        configs, total = await config_service.query_configs(query)
        page_response = PageResponse(
            items=[c.dict() for c in configs],
            total=total,
            page=query.page,
            page_size=query.page_size,
            total_pages=(total + query.page_size - 1) // query.page_size
        )
        return json(BaseResponse(data=page_response.model_dump()).model_dump())
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"查询配置列表失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR
        ).model_dump(), status=500)


@bp.put("/<config_id:int>")
async def update_config(request: Request, config_id: int):
    """更新配置"""
    try:
        data = ConfigDataUpdateRequest(**request.json)
        result = await config_service.update_config(config_id, data)
        if result:
            return json(BaseResponse(data=result.model_dump()).model_dump())
        else:
            return json(BaseResponse(
                code=ErrorCode.NOT_FOUND,
                message=ErrorMessage.NOT_FOUND
            ).model_dump(), status=404)
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"更新配置失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR
        ).model_dump(), status=500)


@bp.delete("/<config_id:int>")
async def delete_config(request: Request, config_id: int):
    """删除配置"""
    try:
        result = await config_service.delete_config(config_id)
        if result:
            return json(BaseResponse(
                code=ErrorCode.SUCCESS,
                message=ErrorMessage.CONFIG_DELETED
            ).model_dump())
        else:
            return json(BaseResponse(
                code=ErrorCode.NOT_FOUND,
                message=ErrorMessage.NOT_FOUND
            ).model_dump(), status=404)
    except Exception as e:
        logger.error(f"删除配置失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR
        ).model_dump(), status=500)