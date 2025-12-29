# -*- coding: utf-8 -*-
"""Sniper 任务模型 - 记录工作流和上下文"""

from enum import Enum
from tortoise.models import Model
from tortoise.fields import (
    CharField, IntField, TextField,
    UUIDField, JSONField, DatetimeField
)
import uuid
from datetime import datetime


class TaskStatus(str, Enum):
    """任务状态枚举"""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Task(Model):
    """
    任务模型 - 核心是记录上下文，供 Agent 查看和继续执行

    设计理念：
    1. 记录任务执行过程中的每一步上下文
    2. Agent 可以查看上下文，决定下一步操作
    3. Service 负责实际执行，Task 负责记录
    """

    id = UUIDField(pk=True, default=uuid.uuid4)
    source_id = CharField(100, description="请求来源ID")
    task_type = CharField(50, description="任务类型")

    # 任务配置（原始请求参数）
    config = JSONField(description="任务配置")
    """
    config 示例:
    {
        "keywords": ["agent面试"],
        "platform": "xiaohongshu",
        "depth": "deep"
    }
    """

    # 状态
    status = CharField(20, default=TaskStatus.PENDING, choices=list(TaskStatus))
    progress = IntField(default=0, description="进度 0-100")

    # 共享上下文 - 所有步骤的结果都记录在这里
    shared_context = JSONField(default=dict, description="共享上下文")
    """
    shared_context 示例 (执行过程中动态填充):
    {
        "step_1_keywords": ["agent面试", "AI面试技巧"],
        "step_2_search_results": [...],
        "step_3_deduplicated_notes": [...],
        "step_4_agent_analysis": {...},
        "final_result": {...}
    }
    """

    # 执行日志 - 记录每一步的输入输出
    logs = JSONField(default=list, description="执行日志")
    """
    logs 示例:
    [
        {
            "step": 1,
            "name": "关键词裂变",
            "timestamp": "2025-12-27 10:00:00",
            "input": {"core_keyword": "agent面试"},
            "output": {"keywords": [...]},
            "status": "completed"
        }
    ]
    """

    # 最终结果
    result = JSONField(null=True, description="最终结果")
    # 错误信息
    error = JSONField(null=True, description="错误信息")

    # 时间戳
    created_at = DatetimeField(auto_now_add=True)
    started_at = DatetimeField(null=True)
    completed_at = DatetimeField(null=True)

    # 元数据
    metadata = JSONField(default=dict, description="元数据")

    class Meta:
        table = "sniper_tasks"
        indexes = [
            ("source_id", "status"),
            ("task_type",),
            ("created_at",),
        ]

    # ===== 辅助方法 =====

    async def log_step(self, step: int, name: str, input_data: dict, output_data: dict, status: str = "completed"):
        """记录一步执行"""
        log_entry = {
            "step": step,
            "name": name,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "input": input_data,
            "output": output_data,
            "status": status
        }
        self.logs.append(log_entry)
        await self.save()

    async def update_context(self, key: str, value: dict):
        """更新共享上下文"""
        self.shared_context[key] = value
        await self.save()

    async def start(self):
        """开始执行"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now()
        await self.save()

    async def complete(self, result_data: dict = None):
        """完成任务"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now()
        if result_data:
            self.result = result_data
        await self.save()

    async def fail(self, error_msg: str, context: dict = None):
        """任务失败"""
        self.status = TaskStatus.FAILED
        self.completed_at = datetime.now()
        self.error = {
            "message": error_msg,
            "context_at_error": context or self.shared_context
        }
        await self.save()

    async def cancel(self):
        """取消任务"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now()
        await self.save()

    def to_agent_readable(self) -> dict:
        """转换为 Agent 可读的格式 - 这是核心！"""
        return {
            "task_id": str(self.id),
            "task_type": self.task_type,
            "status": self.status,
            "progress": self.progress,
            "config": self.config,
            "shared_context": self.shared_context,
            "logs": self.logs,
            "result": self.result,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "next_step_hint": self._get_next_step_hint()
        }

    def _get_next_step_hint(self) -> str:
        """生成下一步操作提示"""
        if self.status == TaskStatus.PENDING:
            return "任务等待开始"
        elif self.status == TaskStatus.RUNNING:
            return f"任务执行中，进度 {self.progress}%，已记录 {len(self.logs)} 步"
        elif self.status == TaskStatus.COMPLETED:
            return "任务已完成，可查看结果"
        elif self.status == TaskStatus.FAILED:
            return f"任务失败: {self.error.get('message') if self.error else '未知错误'}"
        return "未知状态"
