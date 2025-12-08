"""日志工具"""
import sys
import os
from pathlib import Path
from loguru import logger as loguru_logger
from config.settings import settings


class LoggingManager:
    """日志管理器"""
    
    def __init__(self):
        # 移除默认的处理器
        loguru_logger.remove()
        
        # 根据配置设置日志
        self._setup_logging()
    
    def _setup_logging(self):
        """设置日志配置"""
        # 创建日志目录
        log_file_path = Path(settings.log_file_path)
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 控制台输出配置
        if settings.log_to_console:
            console_format = (
                "<green>{time:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
                "<level>{message}</level>"
            )
            
            loguru_logger.add(
                sys.stdout,
                format=console_format,
                level=settings.log_level,
                colorize=True
            )
        
        # 文件输出配置
        if settings.log_to_file:
            file_format = (
                "{time:YYYY-MM-DD HH:mm:ss.SSS} | "
                "{level: <8} | "
                "{name}:{function}:{line} | "
                "{message}"
            )
            
            loguru_logger.add(
                settings.log_file_path,
                format=file_format,
                level=settings.log_level,
                rotation=settings.log_file_rotation,
                retention=settings.log_file_retention,
                compression="zip",
                encoding="utf-8"
            )
    
    def get_logger(self, name: str = None):
        """获取logger实例"""
        if name:
            return loguru_logger.bind(name=name)
        return loguru_logger
    
    def set_level(self, level: str):
        """动态设置日志级别"""
        # 移除所有处理器
        loguru_logger.remove()
        
        # 重新设置
        # 临时修改配置
        old_level = settings.log_level
        settings.log_level = level
        self._setup_logging()
        
        # 恢复配置
        settings.log_level = old_level
    
    def add_handler(self, sink, level: str = None, format: str = None, **kwargs):
        """添加新的日志处理器"""
        if not level:
            level = settings.log_level
        loguru_logger.add(sink, level=level, format=format, **kwargs)


# 创建全局日志管理器实例
logging_manager = LoggingManager()

# 导出logger实例
logger = logging_manager.get_logger()

# 提供便捷函数
def set_log_level(level: str):
    """设置日志级别"""
    logging_manager.set_level(level)

def add_file_handler(
    filepath: str, 
    level: str = None, 
    rotation: str = None,
    retention: str = None
):
    """添加文件日志处理器"""
    logging_manager.add_handler(
        sink=filepath,
        level=level or settings.log_level,
        rotation=rotation or settings.log_file_rotation,
        retention=retention or settings.log_file_retention,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
        encoding="utf-8"
    )