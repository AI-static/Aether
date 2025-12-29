# -*- coding: utf-8 -*-
"""Sniper API 请求/响应模型"""

from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Dict, Any
from models.sniper import TaskStatus, TaskType
from models.connectors import PlatformType


# ==================== 请求模型 ====================

class TrendAnalysisRequest(BaseModel):
    """爆款趋势分析请求"""
    keywords: List[str] = Field(..., description="搜索关键词列表")
    platform: PlatformType = Field(PlatformType.XIAOHONGSHU, description="平台")
    depth: str = Field("deep", description="分析深度: deep(深度) | quick(快速)")
    limit: Optional[int] = Field(50, description="搜索结果限制", ge=1, le=200)

    @field_validator('depth')
    @classmethod
    def validate_depth(cls, v):
        if v not in ['deep', 'quick']:
            raise ValueError('depth 必须是 deep 或 quick')
        return v


class CreatorMonitorRequest(BaseModel):
    """创作者监控请求"""
    creator_ids: List[str] = Field(..., description="创作者ID列表")
    platform: PlatformType = Field(PlatformType.XIAOHONGSHU, description="平台")
    days: Optional[int] = Field(7, description="监控天数", ge=1, le=30)


class TaskQueryRequest(BaseModel):
    """任务查询请求"""
    source_id: Optional[str] = Field(None, description="来源ID，不传则查询所有")
    status: Optional[TaskStatus] = Field(None, description="任务状态过滤")
    task_type: Optional[TaskType] = Field(None, description="任务类型过滤")
    limit: Optional[int] = Field(20, description="返回数量限制", ge=1, le=100)


# ==================== 响应模型 ====================

class TaskResponse(BaseModel):
    """任务响应模型"""
    task_id: str
    status: TaskStatus
    progress: int
    goal: str
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    has_result: bool = False
    has_error: bool = False
    log_count: int = 0


class TaskDetailResponse(BaseModel):
    """任务详情响应"""
    task_id: str
    task_type: TaskType
    status: TaskStatus
    progress: int
    goal: str
    context: Dict[str, Any]
    steps: List[Dict[str, Any]]
    result: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    logs: List[Dict[str, Any]]
    created_at: Optional[str] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Dict[str, Any]


class TaskListResponse(BaseModel):
    """任务列表响应"""
    tasks: List[TaskResponse]
    total: int
    page: int
    page_size: int


class LogStreamResponse(BaseModel):
    """日志流响应"""
    task_id: str
    logs: List[Dict[str, Any]]
    has_more: bool
