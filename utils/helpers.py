"""辅助函数"""
import json
from typing import Any, Dict
from datetime import datetime


def to_json(data: Any) -> str:
    """转换为JSON字符串"""
    try:
        return json.dumps(data, ensure_ascii=False, default=str)
    except Exception as e:
        from utils.logger import logger
        logger.error(f"JSON序列化失败: {e}")
        return "{}"


def from_json(json_str: str) -> Dict:
    """从JSON字符串解析"""
    try:
        return json.loads(json_str)
    except Exception as e:
        from utils.logger import logger
        logger.error(f"JSON解析失败: {e}")
        return {}


def format_timestamp(dt: datetime = None) -> str:
    """格式化时间戳"""
    if dt is None:
        dt = datetime.now()
    return dt.strftime("%Y-%m-%d %H:%M:%S")