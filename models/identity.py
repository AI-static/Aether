"""身份验证相关数据模型"""
from tortoise.models import Model
from tortoise.fields import (
    CharField, IntField, BooleanField, DatetimeField, 
    TextField, UUIDField
)
import uuid
from utils.encryption import encrypt_api_key, decrypt_api_key, verify_api_key, generate_api_key
from utils.logger import logger


class ApiKey(Model):
    """API密钥模型 - 内部服务身份验证"""
    id = UUIDField(pk=True, default=uuid.uuid4)
    source = CharField(50, description="来源类型：system, service, user等")
    source_id = CharField(100, description="来源ID：服务名、用户ID等")
    api_key = CharField(255, unique=True, description="实际的API密钥（已加密）")
    api_key_hash = CharField(64, null=True, description="API密钥的哈希值，用于快速查找")
    name = CharField(200, description="密钥名称/描述")
    
    # 使用限制
    expires_at = DatetimeField(null=True, description="过期时间")
    usage_limit = IntField(null=True, description="使用次数限制")
    usage_count = IntField(default=0, description="已使用次数")
    
    # 状态
    is_active = BooleanField(default=True, description="是否激活")
    
    # 时间戳
    created_at = DatetimeField(auto_now_add=True)
    updated_at = DatetimeField(auto_now=True)
    
    class Meta:
        table = "api_keys"
        indexes = [
            ("source", "source_id", "is_active"),
            ("source", "source_id", "api_key_hash"),
            ("api_key_hash",),
            ("source", "is_active"),
        ]
    
        
    def get_plain_api_key(self) -> str:
        """获取解密后的API密钥"""
        try:
            return decrypt_api_key(self.api_key)
        except Exception as e:
            logger.error(f"解密API密钥失败: {e}")
            raise ValueError("无法解密API密钥")
    
    def verify_key(self, input_key: str) -> bool:
        """验证输入的密钥是否正确"""
        try:
            # 先用哈希快速比较
            import hashlib
            input_hash = hashlib.sha256(input_key.encode()).hexdigest()
            if input_hash != self.api_key_hash:
                return False
            # 再用加密验证
            return verify_api_key(input_key, self.api_key)
        except Exception as e:
            logger.error(f"验证API密钥失败: {e}")
            return False
    
    @classmethod
    async def create_with_generated_key(cls, **kwargs):
        """创建新的API密钥并自动生成密钥值"""
        # 生成新的API密钥
        new_key = generate_api_key()
        
        # 手动加密
        encrypted_key = encrypt_api_key(new_key)
        
        # 生成哈希值
        import hashlib
        api_key_hash = hashlib.sha256(new_key.encode()).hexdigest()
        
        # 保存密钥到数据库
        kwargs['api_key'] = encrypted_key
        kwargs['api_key_hash'] = api_key_hash
        api_key_instance = await cls.create(**kwargs)
        
        # 返回实例和明文密钥（这是唯一一次返回明文的机会）
        return api_key_instance, new_key
    
    async def regenerate_key(self) -> str:
        """重新生成API密钥"""
        # 生成新密钥
        new_key = generate_api_key()
        
        # 加密新密钥
        encrypted_key = encrypt_api_key(new_key)
        
        # 更新数据库
        self.api_key = encrypted_key
        import hashlib
        self.api_key_hash = hashlib.sha256(new_key.encode()).hexdigest()
        await self.save()
        
        # 返回明文密钥
        return new_key


