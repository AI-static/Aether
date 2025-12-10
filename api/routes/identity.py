"""身份验证API路由"""
from sanic import Blueprint, Request
from sanic.response import json
from services.identity_service import identity_service, SourceType
from utils.logger import logger
from api.schema.response import BaseResponse, ErrorCode, ErrorMessage
from api.schema.identity import ApiKeyCreate, ApiKeyUpdate
from utils.exceptions import BusinessException

from pydantic import ValidationError

# 创建蓝图
identity_bp = Blueprint("identity", url_prefix="/identity")


@identity_bp.post("/api-keys")
async def create_api_key(request: Request):
    """创建API密钥（仅系统管理员）"""
    try:
        # 检查权限
        if not hasattr(request, "ctx") or not hasattr(request.ctx, "auth_info"):
            return json(BaseResponse(
                code=ErrorCode.UNAUTHORIZED,
                message=ErrorMessage.UNAUTHORIZED,
                data={"error": "未认证"}
            ).model_dump(), status=401)
        
        auth_info = request.ctx.auth_info
        
        # 只有系统管理员可以创建密钥
        if auth_info.source != SourceType.SYSTEM:
            return json(BaseResponse(
                code=ErrorCode.UNAUTHORIZED,
                message=ErrorMessage.UNAUTHORIZED,
                data={"error": "只有系统管理员可以创建API密钥"}
            ).model_dump(), status=403)
        
        key_create = ApiKeyCreate(**request.json)
        logger.info(f"创建API密钥请求: {key_create}")
        
        api_key_info, plain_api_key = await identity_service.create_api_key(
            key_create, 
            creator_source=auth_info.source,
            creator_source_id=auth_info.source_id
        )

        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=ErrorMessage.API_KEY_CREATE_SUCCESS,
            data={
                **api_key_info.model_dump(),
                "api_key": plain_api_key  # 只在创建时返回一次明文密钥
            }
        ).model_dump())
            
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"创建API密钥失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@identity_bp.put("/api-keys/<key_id>")
async def update_api_key(request: Request, key_id: str):
    """更新API密钥"""
    try:
        # 从认证中间件获取认证信息
        if not hasattr(request, "ctx") or not hasattr(request.ctx, "auth_info"):
            return json(BaseResponse(
                code=ErrorCode.UNAUTHORIZED,
                message=ErrorMessage.UNAUTHORIZED,
                data={"error": "未认证"}
            ).model_dump(), status=401)
        
        auth_info = request.ctx.auth_info
        
        # 解析更新数据
        update_data = ApiKeyUpdate(**request.json)
        
        # 转换为字典，过滤掉None值
        update_dict = {k: v for k, v in update_data.model_dump().items() if v is not None}
        
        # 更新API密钥
        await identity_service.update_api_key(
            key_id, 
            auth_info.source, 
            auth_info.source_id, 
            **update_dict
        )
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=ErrorMessage.API_KEY_UPDATE_SUCCESS,
            data={"success": True}
        ).model_dump())
        
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except BusinessException as e:
        logger.warning(f"更新API密钥业务错误: {e}")
        return json(BaseResponse(
            code=e.code,
            message=e.message,
            data={"error": e.message}
        ).model_dump(), status=404 if e.code == ErrorCode.NOT_FOUND else 400)
    except Exception as e:
        logger.error(f"更新API密钥失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@identity_bp.get("/api-keys")
async def list_api_keys(request: Request):
    """获取API密钥列表"""
    try:
        # 从认证中间件获取认证信息
        if not hasattr(request, "ctx") or not hasattr(request.ctx, "auth_info"):
            return json(BaseResponse(
                code=ErrorCode.UNAUTHORIZED,
                message=ErrorMessage.UNAUTHORIZED,
                data={"error": "未认证"}
            ).model_dump(), status=401)
        
        auth_info = request.ctx.auth_info
        
        # 系统管理员可以获取所有密钥
        if auth_info.source == "system":
            api_keys = await identity_service.get_all_api_keys()
        else:
            # 其他用户只能获取自己的密钥
            api_keys = await identity_service.get_source_api_keys(
                auth_info.source, 
                auth_info.source_id
            )
        
        # 转换为响应格式
        api_keys_data = [api_key.model_dump() for api_key in api_keys]
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message="获取API密钥列表成功",
            data={
                "api_keys": api_keys_data,
                "total": len(api_keys_data)
            }
        ).model_dump())
        
    except Exception as e:
        logger.error(f"获取API密钥列表失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@identity_bp.delete("/api-keys/<key_id>")
async def revoke_api_key(request: Request, key_id: str):
    """撤销API密钥"""
    try:
        # 从认证中间件获取认证信息
        if not hasattr(request, "ctx") or not hasattr(request.ctx, "auth_info"):
            return json(BaseResponse(
                code=ErrorCode.UNAUTHORIZED,
                message=ErrorMessage.UNAUTHORIZED,
                data={"error": "未认证"}
            ).model_dump(), status=401)
        
        auth_info = request.ctx.auth_info
        
        # 撤销API密钥
        success, error = await identity_service.revoke_api_key(
            key_id, 
            auth_info.source, 
            auth_info.source_id
        )
        
        if not success:
            return json(BaseResponse(
                code=ErrorCode.NOT_FOUND,
                message=ErrorMessage.NOT_FOUND,
                data={"error": error or "API密钥不存在"}
            ).model_dump(), status=404)
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=ErrorMessage.API_KEY_REVOKE_SUCCESS,
            data={"success": True}
        ).model_dump())
        
    except Exception as e:
        logger.error(f"撤销API密钥失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)
