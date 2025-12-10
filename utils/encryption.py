"""加密工具模块 - 提供AES-256加密/解密功能"""

import base64
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from typing import Optional, Tuple
import secrets
from utils.logger import logger


class AESEncryption:
    """AES-256-GCM 加密/解密工具类"""
    
    def __init__(self, master_key: str):
        """
        初始化加密工具
        
        Args:
            master_key: 主密钥（必须是32字节的十六进制字符串）
        """
        # 将十六进制字符串转换为字节
        try:
            self.master_key = bytes.fromhex(master_key)
        except ValueError:
            raise ValueError("master_key 必须是十六进制字符串")
        
        # 验证密钥长度必须是32字节（256位）
        if len(self.master_key) != 32:
            raise ValueError(f"master_key 必须是32字节（256位），当前长度: {len(self.master_key)}字节")
    
    def encrypt(self, plaintext: str) -> str:
        """
        加密文本
        
        Args:
            plaintext: 要加密的文本
            
        Returns:
            base64编码的加密数据 (nonce + ciphertext + tag)
        """
        try:
            # 生成随机nonce
            nonce = secrets.token_bytes(12)  # 96位nonce
            
            # 创建AESGCM实例
            aesgcm = AESGCM(self.master_key)
            
            # 加密数据
            ciphertext = aesgcm.encrypt(nonce, plaintext.encode(), None)
            
            # 组合nonce和密文
            encrypted_data = nonce + ciphertext
            
            # 返回base64编码的结果
            return base64.b64encode(encrypted_data).decode()
            
        except Exception as e:
            logger.error(f"加密失败: {e}")
            raise ValueError(f"加密失败: {e}")
    
    def decrypt(self, encrypted_data_b64: str) -> str:
        """
        解密数据
        
        Args:
            encrypted_data_b64: base64编码的加密数据
            
        Returns:
            解密后的文本
        """
        try:
            # Base64解码
            encrypted_data = base64.b64decode(encrypted_data_b64)
            
            # 分离nonce和密文
            nonce = encrypted_data[:12]  # 前12字节是nonce
            ciphertext = encrypted_data[12:]  # 剩余的是密文
            
            # 创建AESGCM实例
            aesgcm = AESGCM(self.master_key)
            
            # 解密数据
            plaintext = aesgcm.decrypt(nonce, ciphertext, None)
            
            return plaintext.decode()
            
        except Exception as e:
            logger.error(f"解密失败: {e}")
            raise ValueError(f"解密失败: {e}")
    
    def generate_key(self) -> str:
        """
        生成随机API密钥
        
        Returns:
            新的API密钥
        """
        return f"ak-{secrets.token_hex(16)}"
    
    def verify_key(self, input_key: str, stored_encrypted: str) -> bool:
        """
        验证密钥是否匹配
        
        Args:
            input_key: 输入的密钥
            stored_encrypted: 存储的加密密钥
            
        Returns:
            是否匹配
        """
        try:
            decrypted = self.decrypt(stored_encrypted)
            return secrets.compare_digest(input_key, decrypted)
        except Exception:
            return False


# 全局加密实例
_encryption_instance = None


def get_encryption() -> AESEncryption:
    """获取全局加密实例"""
    global _encryption_instance
    if _encryption_instance is None:
        from config.settings import settings
        if not settings.encryption_master_key:
            raise ValueError("未设置 encryption_master_key 配置")
        _encryption_instance = AESEncryption(settings.encryption_master_key)
    return _encryption_instance


def encrypt_api_key(api_key: str) -> str:
    """加密API密钥"""
    return get_encryption().encrypt(api_key)


def decrypt_api_key(encrypted_key: str) -> str:
    """解密API密钥"""
    return get_encryption().decrypt(encrypted_key)


def generate_api_key() -> str:
    """生成新的API密钥"""
    return get_encryption().generate_key()


def verify_api_key(input_key: str, stored_encrypted: str) -> bool:
    """验证API密钥"""
    return get_encryption().verify_key(input_key, stored_encrypted)