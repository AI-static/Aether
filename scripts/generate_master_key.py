#!/usr/bin/env python3
"""生成加密主密钥脚本"""

import secrets

def generate_master_key():
    """生成32字节（256位）的十六进制主密钥"""
    # 生成32字节的随机数据
    key_bytes = secrets.token_bytes(32)
    # 转换为十六进制字符串（64个字符）
    key_hex = key_bytes.hex()
    
    print("🔐 生成的加密主密钥：")
    print("=" * 60)
    print(key_hex)
    print("=" * 60)
    print(f"长度: {len(key_bytes)} 字节 ({len(key_bytes) * 8} 位)")
    print("\n请将此密钥添加到您的环境变量或 .env 文件中：")
    print(f"ENCRYPTION_MASTER_KEY={key_hex}")
    print("\n⚠️  重要提示：")
    print("1. 请妥善保管此主密钥，丢失后将无法解密已加密的数据！")
    print("2. 不要将此密钥提交到版本控制系统！")
    print("3. 建议使用密钥管理服务（如 AWS KMS、HashiCorp Vault）存储此密钥")

if __name__ == "__main__":
    generate_master_key()