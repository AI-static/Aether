# -*- coding: utf-8 -*-
"""Human-in-Loop 交互模型"""

from datetime import datetime
from enum import Enum
from typing import Dict, Any, Optional
from uuid import uuid4
from pydantic import BaseModel, Field


class InteractionType(str, Enum):
    """交互类型枚举"""
    LOGIN_CONFIRM = "login_confirm"        # 登录确认
    CONTENT_REVIEW = "content_review"      # 内容审核
    IMAGE_SELECT = "image_select"          # 图片选择
    TEXT_EDIT = "text_edit"                # 文本编辑
    CHOICE_SELECT = "choice_select"        # 选项选择
    CUSTOM_APPROVAL = "custom_approval"    # 自定义审批


class InteractionStatus(str, Enum):
    """交互状态枚举"""
    PENDING = "pending"      # 等待用户响应
    CONFIRMED = "confirmed"  # 用户确认
    REJECTED = "rejected"    # 用户拒绝
    CANCELLED = "cancelled"  # 取消
    TIMEOUT = "timeout"      # 超时


class HumanInteraction(BaseModel):
    """通用的人机交互信息

    用于记录所有需要人类介入的任务交互，包括登录、审核、选择等场景
    """

    # 基本信息
    interaction_id: str = Field(default_factory=lambda: str(uuid4()))
    interaction_type: InteractionType
    status: InteractionStatus = InteractionStatus.PENDING

    # 任务关联
    task_id: str
    task_step: int = 0  # 在第几步需要交互

    # 交互数据（JSON，根据类型不同而不同）
    # 登录: {"qrcode_url": "xxx", "context_id": "xxx", "platform": "xiaohongshu"}
    # 审核: {"content": "xxx", "images": ["url1", "url2"]}
    # 选择: {"options": ["A", "B", "C"], "max_select": 2}
    data: Dict[str, Any] = {}

    # 用户响应
    user_response: Optional[Dict[str, Any]] = None
    user_comment: Optional[str] = None  # 用户备注（如拒绝原因）

    # 时间控制
    created_at: datetime = Field(default_factory=datetime.now)
    timeout_seconds: int = 120  # 超时时间（秒）
    expires_at: Optional[datetime] = None

    # 恢复点（任务重试时从这里继续）
    resume_point: Optional[str] = None  # 保存函数名或步骤标识

    # 元数据（扩展信息）
    metadata: Dict[str, Any] = {}

    class Config:
        from_attributes = True  # Pydantic v2
        use_enum_values = True


class InteractionResponse(BaseModel):
    """交互响应"""
    success: bool
    interaction: Optional[HumanInteraction] = None
    message: str = ""


class UserConfirmRequest(BaseModel):
    """用户确认请求"""
    interaction_id: str
    confirmed: bool  # True=确认, False=拒绝
    response_data: Optional[Dict[str, Any]] = None  # 额外的响应数据（如选择的选项）
    comment: Optional[str] = None  # 用户备注