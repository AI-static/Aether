"""身份验证服务"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple
import uuid
from tortoise.exceptions import IntegrityError, DoesNotExist
from models.identity import ApiKey
from utils.logger import logger
from utils.exceptions import BusinessException
from api.schema.base import ErrorCode
from api.schema.identity import ApiKeyCreate, ApiKeyInfo, SourceType
from utils.encryption import encrypt_api_key, decrypt_api_key, verify_api_key, generate_api_key


class IdentityService:
    """身份验证服务"""
    
    async def create_api_key(self, key_data: ApiKeyCreate, creator_source: str = None, creator_source_id: str = None) -> Tuple[ApiKeyInfo, str]:
        """
        创建API密钥
        
        Returns:
            Tuple[ApiKeyInfo, str]: (API密钥信息, 明文密钥) - 明文密钥只在创建时返回一次
            
        Raises:
            BusinessException: 业务异常
        """
        try:
            # 权限检查：只有系统管理员可以创建密钥
            if creator_source != SourceType.SYSTEM.value:
                raise BusinessException(
                    message="只有系统管理员可以创建API密钥",
                    code=ErrorCode.UNAUTHORIZED
                )
            
            # 使用模型的自动加密功能创建密钥
            api_key_obj, plain_api_key = await ApiKey.create_with_generated_key(
                source=key_data.source.value,
                source_id=key_data.source_id or "default",
                name=key_data.name,
                expires_at=key_data.expires_at,
                usage_limit=key_data.usage_limit
            )
            
            logger.info(f"api_key ------> {plain_api_key}")
            
            # 转换为响应对象
            result = ApiKeyInfo(
                id=str(api_key_obj.id),
                source=api_key_obj.source,
                source_id=api_key_obj.source_id,
                name=api_key_obj.name,
                expires_at=api_key_obj.expires_at,
                usage_limit=api_key_obj.usage_limit,
                usage_count=api_key_obj.usage_count,
                is_active=api_key_obj.is_active,
                created_at=api_key_obj.created_at,
                updated_at=api_key_obj.updated_at
            )
            
            logger.info(f"创建API密钥成功: {api_key_obj.id} for {key_data.source}:{key_data.source_id}")
            return result, plain_api_key
            
        except IntegrityError as e:
            logger.error(f"创建API密钥失败，数据冲突: {e}")
            raise BusinessException(
                message="数据冲突，可能是重复的key_id或api_key",
                code=ErrorCode.CREATE_FAILED
            )
        except Exception as e:
            logger.error(f"创建API密钥失败: {e}")
            raise BusinessException(
                message=f"创建失败: {str(e)}",
                code=ErrorCode.INTERNAL_ERROR
            )

    @staticmethod
    async def validate_auth(api_key: str) -> ApiKeyInfo:
        """
        验证API密钥
        
        Args:
            api_key: API密钥
            
        Returns:
            ApiKeyInfo: API密钥信息
            
        Raises:
            ValueError: API密钥相关错误
            Exception: 系统错误
        """
        if not api_key:
            raise ValueError("API密钥不能为空")
        
        if not api_key.startswith("ak-"):
            raise ValueError("API密钥格式错误，应以 'ak-' 开头")
        
        # 使用哈希值快速查找
        import hashlib
        api_key_hash = hashlib.sha256(api_key.encode()).hexdigest()
        
        # 查找API密钥
        api_key_obj = await ApiKey.get_or_none(api_key_hash=api_key_hash, is_active=True).prefetch_related()
        
        if not api_key_obj:
            # 检查是否存在但被禁用
            disabled_key = await ApiKey.get_or_none(api_key_hash=api_key_hash, is_active=False)
            if disabled_key:
                raise ValueError(f"API密钥已被禁用: {disabled_key.id}")
            raise ValueError("API密钥不存在或已失效")
        
        # 检查过期时间
        if api_key_obj.expires_at and api_key_obj.expires_at < datetime.now(timezone.utc):
            raise ValueError(f"API密钥已于 {api_key_obj.expires_at.strftime('%Y-%m-%d %H:%M:%S')} 过期")
        
        # 检查使用次数限制
        if api_key_obj.usage_limit and api_key_obj.usage_count >= api_key_obj.usage_limit:
            raise ValueError(f"API密钥使用次数已达上限 ({api_key_obj.usage_count}/{api_key_obj.usage_limit})")
        
        # 更新使用次数
        api_key_obj.usage_count += 1
        await api_key_obj.save()
        
        # 转换为响应对象
        result = ApiKeyInfo(
            id=str(api_key_obj.id),
            source=api_key_obj.source,
            source_id=api_key_obj.source_id,
            name=api_key_obj.name,
            expires_at=api_key_obj.expires_at,
            usage_limit=api_key_obj.usage_limit,
            usage_count=api_key_obj.usage_count,
            is_active=api_key_obj.is_active,
            created_at=api_key_obj.created_at,
            updated_at=api_key_obj.updated_at
        )
        
        logger.info(f"API密钥验证成功: {api_key_obj.source}:{api_key_obj.source_id}")
        return result
    
    async def get_source_api_keys(self, source: str, source_id: str) -> List[ApiKeyInfo]:
        """获取指定来源的API密钥列表"""
        try:
            query = ApiKey.filter(source=source, source_id=source_id, is_active=True)
            
            api_keys = await query.order_by('-created_at')
            
            result = []
            for api_key_obj in api_keys:
                result.append(ApiKeyInfo(
                    id=str(api_key_obj.id),
                    source=api_key_obj.source,
                    source_id=api_key_obj.source_id,
                    name=api_key_obj.name,
                    expires_at=api_key_obj.expires_at,
                    usage_limit=api_key_obj.usage_limit,
                    usage_count=api_key_obj.usage_count,
                    is_active=api_key_obj.is_active,
                    created_at=api_key_obj.created_at,
                    updated_at=api_key_obj.updated_at
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"获取API密钥列表失败: {e}")
            return []
    
    async def get_all_api_keys(self) -> List[ApiKeyInfo]:
        """获取所有API密钥列表（仅系统管理员可用）"""
        try:
            api_keys = await ApiKey.filter(is_active=True).order_by('-created_at')
            
            result = []
            for api_key_obj in api_keys:
                result.append(ApiKeyInfo(
                    id=str(api_key_obj.id),
                    source=api_key_obj.source,
                    source_id=api_key_obj.source_id,
                    name=api_key_obj.name,
                    expires_at=api_key_obj.expires_at,
                    usage_limit=api_key_obj.usage_limit,
                    usage_count=api_key_obj.usage_count,
                    is_active=api_key_obj.is_active,
                    created_at=api_key_obj.created_at,
                    updated_at=api_key_obj.updated_at
                ))
            
            return result
            
        except Exception as e:
            logger.error(f"获取所有API密钥列表失败: {e}")
            return []
    
    async def update_api_key(self, key_id: str, source: SourceType, source_id: str, **kwargs):
        """更新API密钥"""
        # 系统管理员可以更新任何密钥
        if source == SourceType.SYSTEM:
            api_key_obj = await ApiKey.get_or_none(id=key_id)
        else:
            api_key_obj = await ApiKey.get_or_none(id=key_id, source=source, source_id=source_id)
            
        if not api_key_obj:
            raise BusinessException(
                message="API密钥不存在",
                code=ErrorCode.NOT_FOUND
            )
        
        # 更新字段
        for field, value in kwargs.items():
            if hasattr(api_key_obj, field) and value is not None:
                setattr(api_key_obj, field, value)
        
        await api_key_obj.save()
        logger.info(f"更新API密钥成功: {key_id}")
    
    async def revoke_api_key(self, key_id: str, source: str, source_id: str = None) -> Tuple[bool, Optional[str]]:
        """撤销API密钥"""
        try:
            # 如果是系统管理员，可以撤销任何密钥
            if source == SourceType.SYSTEM.value:
                api_key_obj = await ApiKey.get_or_none(id=key_id)
            else:
                api_key_obj = await ApiKey.get_or_none(id=key_id, source=source, source_id=source_id)
            
            if not api_key_obj:
                return False, "API密钥不存在"
            
            api_key_obj.is_active = False
            await api_key_obj.save()
            
            logger.info(f"撤销API密钥成功: {key_id}")
            return True, None
            
        except Exception as e:
            logger.error(f"撤销API密钥失败: {e}")
            return False, f"撤销失败: {str(e)}"


# 创建全局服务实例
identity_service = IdentityService()