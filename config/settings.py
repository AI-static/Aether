from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用配置
    app_name: str = "Aether"
    app_description: str = "业务适配层服务"  # 应用描述
    app_port: int = 8000
    app_debug: bool = False
    app_auto_reload: bool = False

    # 日志配置
    log_level: str = "INFO"  # 日志级别: DEBUG, INFO, WARNING, ERROR, CRITICAL
    log_to_file: bool = True  # 是否写入文件
    log_to_console: bool = True  # 是否输出到控制台
    log_file_path: str = "logs/app.log"  # 日志文件路径
    log_file_rotation: str = "1 day"  # 日志轮转: 1 day, 1 week, 1 month
    log_file_retention: str = "30 days"  # 日志保留时间

    pg_host: str = "localhost"
    pg_port: int = 5432
    pg_user: str = None
    pg_password: str = ""
    pg_database: str = 'aether'
    
    # 其他服务配置
    ezlink_base_url: Optional[str] = "https://api.ezlinkai.com/v1"
    ezlink_api_key: Optional[str] = None

    vectorai_base_url: Optional[str] = "https://api.vectortara.com/v1"
    vectorai_api_key: Optional[str] = None  # VectorAI API密钥

    agentbay_api_key: Optional[str] = ""
    # 加密配置
    encryption_master_key: Optional[str] = None  # 32字节十六进制字符串，用于API密钥加密
    
    # OSS配置
    oss_access_key_id: Optional[str] = None  # OSS访问密钥ID
    oss_access_key_secret: Optional[str] = None  # OSS访问密钥Secret
    oss_endpoint: str = "https://oss-cn-hangzhou.aliyuncs.com"  # OSS端点
    oss_bucket_name: Optional[str] = None  # OSS存储桶名称

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


# 创建全局配置实例
settings = Settings()

# 兼容旧代码的引用
global_settings = settings



def create_db_config() -> dict:
    return {
        "connections": {
            "default": {
                "engine": "tortoise.backends.asyncpg",
                "credentials": {
                    "host": global_settings.pg_host,
                    "port": global_settings.pg_port,
                    "user": global_settings.pg_user,
                    "password": global_settings.pg_password,
                    "database": global_settings.pg_database,
                    "schema": "public",
                    "maxsize": 500,
                    "minsize": 10,
                    "command_timeout": 30,  # 增加超时时间
                    "server_settings": {
                        # PostgreSQL服务器设置
                        "application_name": global_settings.app_name,
                        "tcp_keepalives_idle": "300",
                        "tcp_keepalives_interval": "30",
                        "tcp_keepalives_count": "3",
                    },
                    # SSL设置（可能影响性能）
                    "ssl": "prefer",  # 或 False, True, "require"
                }
            }
        },
        "apps": {
            "models": {
                "models": [
                    "models.identity",
                ],
                "default_connection": "default"
            }
        },
        "use_tz": False,
        "timezone": "Asia/Shanghai",
    }