#!/usr/bin/env python3
"""系统初始化脚本 - 创建系统管理员API密钥"""

import asyncio
import sys
import os
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from tortoise import Tortoise
from models.identity import ApiKey
from utils.logger import logger


async def init_database():
    """初始化数据库连接"""
    from config.settings import create_db_config
    
    await Tortoise.init(config=create_db_config())
    await Tortoise.generate_schemas()


async def create_system_admin_key():
    """创建系统管理员API密钥"""
    try:
        # 检查是否已存在系统管理员密钥
        existing_key = await ApiKey.get_or_none(
            source="system", 
            source_id="system", 
            is_active=True
        )
        
        if existing_key:
            # 尝试解密显示（如果可能）
            try:
                plain_key = existing_key.get_plain_api_key()
                logger.info(f"系统管理员密钥已存在: {plain_key}")
                return plain_key
            except:
                logger.info(f"系统管理员密钥已存在（已加密存储）")
                return "[已加密存储]"
        
        # 使用模型的加密功能创建系统管理员密钥
        admin_key, plain_key = await ApiKey.create_with_generated_key(
            source="system",
            source_id="system",
            name="系统管理员密钥",
            is_active=True
        )
        
        logger.info(f"✅ 成功创建系统管理员密钥: {plain_key}")
        print("\n" + "="*60)
        print("⚠️  重要提示：请妥善保管以下系统管理员API密钥")
        print("="*60)
        print(f"API Key: {plain_key}")
        print("="*60)
        print("\n使用方法：")
        print("curl -H 'Authorization: Bearer " + plain_key + "' \\")
        print("     -H 'Content-Type: application/json' \\")
        print("     -X POST http://localhost:8000/identity/api-keys \\")
        print("     -d '{\"source\": \"service\", \"source_id\": \"my-service\", \"name\": \"我的服务密钥\"}'")
        print("\n该密钥拥有创建、查看、更新、删除所有API密钥的权限！")
        print("\n✅ 密钥已使用AES-256加密安全存储")
        
        return plain_key
        
    except Exception as e:
        logger.error(f"创建系统管理员密钥失败: {e}")
        raise


async def main():
    """主函数"""
    print("🚀 开始初始化系统...")
    
    try:
        # 初始化数据库
        await init_database()
        logger.info("数据库初始化成功")
        
        # 创建系统管理员密钥
        await create_system_admin_key()
        
        print("\n✅ 系统初始化完成！")
        
    except Exception as e:
        logger.error(f"系统初始化失败: {e}")
        print(f"\n❌ 初始化失败: {e}")
        sys.exit(1)
    
    finally:
        # 关闭数据库连接
        await Tortoise.close_connections()


if __name__ == "__main__":
    # 设置事件循环策略（macOS 兼容性）
    if sys.platform == 'darwin':
        import asyncio
        asyncio.set_event_loop_policy(asyncio.DefaultEventLoopPolicy())
    
    asyncio.run(main())