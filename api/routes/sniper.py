# -*- coding: utf-8 -*-
"""Sniper API 路由 - 支持 Agent/Workflow 任务执行"""

from sanic import Blueprint, Request
from sanic.response import json
import asyncio

from api.schema.base import BaseResponse, ErrorCode
from services.task_service import TaskService
from utils.logger import logger

# 导入所有 Agent 类
from services.sniper.xhs_trend import XiaohongshuTrendAgent
from services.sniper.xhs_creator import CreatorSniper
from services.sniper.douyin_trend import DouyinDeepAgent
from config.settings import global_settings

sniper_bp = Blueprint("sniper", url_prefix="/sniper")

# Agent 时间节省配置（与 list_agents 保持一致）
AGENT_TIME_SAVINGS: dict[str, int] = {
    "xhs_trend_agent": 85,
    "xhs_creator_sniper": 25,
    "douyin_trend_agent": 85,
    "douyin_creator_sniper": 25,
}

# Agent/Workflow 映射表 - 直接存储类对象
AGENT_WORKFLOW_MAPPING = {
    # 小红书 Agent
    "xhs_trend_agent": XiaohongshuTrendAgent,
    "xhs_creator_sniper": CreatorSniper,

    # 抖音 Agent
    "douyin_trend_agent": DouyinDeepAgent,

    # 可以继续添加更多 Agent 和 Workflow
    # "custom_workflow": CustomWorkflow,
}


@sniper_bp.post("/execute")
async def execute_agent(request: Request):
    """执行 Agent/Workflow 任务（统一入口）

    Body:
        agent_or_workflow: Agent/Workflow 唯一标识（如 "xhs_trend_agent"）
        params: 传递给 Agent 的参数（如 {"keywords": ["美食", "旅游"]}）
    """
    try:
        from models.task import Task

        data = request.json
        agent_id = data.get("agent_or_workflow")
        params = data.get("params", {})

        if not agent_id:
            return json(BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message="agent_or_workflow 不能为空",
                data=None
            ).model_dump(), status=400)

        if agent_id not in AGENT_WORKFLOW_MAPPING:
            return json(BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"不支持的 Agent/Workflow: {agent_id}",
                data=None
            ).model_dump(), status=400)

        auth_info = request.ctx.auth_info

        # 创建任务
        task = await Task.create(
            source=auth_info.source.value,
            source_id=auth_info.source_id,
            task_type=agent_id,
            params=params
        )
        await task.start()

        # 获取 Agent 类
        agent_class = AGENT_WORKFLOW_MAPPING[agent_id]

        # 在后台执行 Agent
        asyncio.create_task(_run_agent_task(agent_class, request, task, **params))

        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message="任务已创建",
            data={
                "task_id": str(task.id),
                "agent_or_workflow": agent_id,
                "message": f"{agent_id} 任务已在后台执行"
            }
        ).model_dump())

    except Exception as e:
        logger.error(f"执行 Agent 任务失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            data=None
        ).model_dump(), status=500)


async def _run_agent_task(agent_class, request: Request, task, **kwargs):
    """在后台运行 Agent 任务

    Args:
        agent_class: Agent 类对象
        request: Sanic Request 对象
        task: 任务对象
        **kwargs: 传递给 Agent 的参数
    """
    try:
        # 创建实例
        auth_info = request.ctx.auth_info
        agent = agent_class(
            source_id=auth_info.source_id,
            source=auth_info.source.value,
            playwright=request.app.ctx.playwright,
            task=task
        )

        # 设置超时时间（优先使用 Agent 类的配置，否则使用全局配置）
        timeout_seconds = getattr(agent, 'timeout_seconds', global_settings.task.timeout)

        # 使用 asyncio.wait_for 添加超时控制
        try:
            await asyncio.wait_for(
                agent.execute(**kwargs),
                timeout=timeout_seconds
            )
        except asyncio.TimeoutError:
            logger.error(f"Agent {agent_class.__name__} 执行超时（{timeout_seconds}秒）")
            await task.fail(f"任务执行超时（{timeout_seconds}秒）", progress=task.progress)
            return

    except Exception as e:
        import traceback
        logger.error(f"Agent {agent_class.__name__} 执行失败: {traceback.format_exc()}")
        await task.fail(str(e), 0)


@sniper_bp.get("/task/<task_id:str>")
async def get_task(request: Request, task_id: str):
    """获取任务详情"""
    task_service = TaskService()
    task = await task_service.get_task(task_id)

    if not task:
        return json(BaseResponse(
            code=ErrorCode.NOT_FOUND,
            message="任务不存在",
            data=None
        ).model_dump(), status=404)

    return json(BaseResponse(
        code=ErrorCode.SUCCESS,
        message="获取成功",
        data=task.to_agent_readable()
    ).model_dump())


@sniper_bp.post("/task/<task_id:str>/retry")
async def retry_task(request: Request, task_id: str):
    """重试任务"""
    try:
        from models.task import Task, TaskStatus

        # 获取原任务（会复用此任务对象）
        task = await Task.get_or_none(id=task_id)
        if not task:
            return json(BaseResponse(
                code=ErrorCode.NOT_FOUND,
                message="任务不存在",
                data=None
            ).model_dump(), status=404)

        # 获取 Agent 类
        agent_id = task.task_type
        if agent_id not in AGENT_WORKFLOW_MAPPING:
            return json(BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"不支持的 Agent/Workflow: {agent_id}",
                data=None
            ).model_dump(), status=400)

        # 重置任务状态（复用原任务对象）
        task.status = TaskStatus.RUNNING
        task.progress = 0
        task.error = None
        task.result = None
        task.started_at = None
        task.completed_at = None
        # logs 保留，作为历史记录参考
        await task.save()

        # 获取原参数
        original_params = task.params or {}

        # 获取 Agent 类
        agent_class = AGENT_WORKFLOW_MAPPING[agent_id]

        # 在后台执行 Agent，复用同一个 task
        asyncio.create_task(_run_agent_task(agent_class, request, task, **original_params))

        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message="任务已重新开始",
            data={
                "task_id": str(task.id),
                "agent_or_workflow": agent_id,
                "message": f"{agent_id} 任务已重新开始执行"
            }
        ).model_dump())
    except Exception as e:
        logger.error(f"重试任务失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            data=None
        ).model_dump(), status=500)


@sniper_bp.get("/task/<task_id:str>/logs")
async def get_logs(request: Request, task_id: str):
    """获取日志流"""
    offset = int(request.args.get("offset", 0))
    task_service = TaskService()
    data = await task_service.get_task_logs(task_id, offset)

    return json(BaseResponse(
        code=ErrorCode.SUCCESS,
        message="获取成功",
        data=data
    ).model_dump())


@sniper_bp.post("/tasks")
async def list_tasks(request: Request):
    """查询任务列表"""
    data = request.json or {}
    auth_info = request.ctx.auth_info
    task_service = TaskService()

    tasks = await task_service.list_tasks(
        source=data.get("source") or auth_info.source.value,
        source_id=data.get("source_id") or auth_info.source_id,
        status=data.get("status"),
        task_type=data.get("task_type"),
        limit=data.get("limit", 20)
    )

    return json(BaseResponse(
        code=ErrorCode.SUCCESS,
        message="获取成功",
        data={
            "tasks": [task.to_agent_readable() for task in tasks],
            "total": len(tasks)
        }
    ).model_dump())


@sniper_bp.get("/agents")
async def list_agents(request: Request):
    """获取所有可用的 Agent 和 Workflow"""
    agents = [
        {
            "id": "xhs_trend_agent",
            "display_name": "小红书趋势追踪",
            "description": "小红书平台爆款趋势追踪与分析",
            "platform": "xiaohongshu",
            "icon": "fas fa-chart-line",
            "tags": ["Trend", "Analysis"],
            "params": {
                "keywords": {
                    "type": "list[str]",
                    "required": True,
                    "description": "分析关键词列表",
                    "placeholder": "每行一个关键词\n杭州旅游\nPython教程\nAI工具"
                }
            }
        },
        {
            "id": "xhs_creator_sniper",
            "display_name": "小红书创作者监控",
            "description": "监控小红书指定创作者的最新内容动态",
            "platform": "xiaohongshu",
            "icon": "fas fa-user-astronaut",
            "tags": ["Monitor", "Creator"],
            "params": {
                "creator_ids": {
                    "type": "list[str]",
                    "required": True,
                    "description": "创作者ID列表",
                    "placeholder": "每行一个创作者ID\n5c4c5848000000001200de55\n657f31eb000000003d036737"
                },
                "latency": {
                    "type": "int",
                    "required": False,
                    "description": "监控天数",
                    "default": 7,
                    "min": 1,
                    "max": 30
                }
            }
        },
        {
            "id": "douyin_trend_agent",
            "display_name": "抖音趋势追踪",
            "description": "抖音平台爆款趋势追踪与分析",
            "platform": "douyin",
            "icon": "fas fa-chart-line",
            "tags": ["Trend", "Analysis"],
            "params": {
                "keywords": {
                    "type": "list[str]",
                    "required": True,
                    "description": "分析关键词列表",
                    "placeholder": "每行一个关键词\nagent interview\nPython tutorial\nAI tools"
                }
            }
        },
        {
            "id": "douyin_creator_sniper",
            "display_name": "抖音创作者监控",
            "description": "监控抖音指定创作者的最新内容动态",
            "platform": "douyin",
            "icon": "fas fa-user-astronaut",
            "tags": ["Monitor", "Creator"],
            "params": {
                "creator_ids": {
                    "type": "list[str]",
                    "required": True,
                    "description": "创作者ID列表",
                    "placeholder": "每行一个创作者ID"
                }
            }
        }
    ]

    for agent in agents:
        agent["time_savings"] = AGENT_TIME_SAVINGS.get(str(agent.get("id", "")), "0")

    return json(BaseResponse(
        code=ErrorCode.SUCCESS,
        message="获取成功",
        data={"agents": agents, "total": len(agents)}
    ).model_dump())


def format_savings(minutes: int) -> str:
    """格式化时间节省显示

    Args:
        minutes: 分钟数

    Returns:
        格式化后的字符串，如 "2h 30m" 或 "45m"
    """
    if minutes >= 60:
        hours = minutes // 60
        mins = minutes % 60
        return f"{hours}h {mins}m" if mins > 0 else f"{hours}h"
    return f"{minutes}m"


@sniper_bp.get("/time-savings")
async def get_time_savings(request: Request):
    """获取累计节约时间

    Returns:
        {
            "total_savings_minutes": 360,
            "total_savings_formatted": "6h 0m",
            "task_count": 5,
            "breakdown": {
                "xhs_trend_agent": {"count": 3, "savings": 360},
                "xhs_creator_sniper": {"count": 2, "savings": 120}
            }
        }
    """
    try:
        from models.task import Task, TaskStatus

        auth_info = request.ctx.auth_info
        task_service = TaskService()

        # 获取所有已完成的任务
        completed_tasks = await task_service.list_tasks(
            source=auth_info.source.value,
            source_id=auth_info.source_id,
            status=TaskStatus.COMPLETED,
            limit=1000
        )

        total_savings = 0
        breakdown = {}

        for task in completed_tasks:
            task_type = task.task_type

            # 从配置中获取该 agent 的时间节省值
            time_savings = AGENT_TIME_SAVINGS.get(task_type, 0)
            total_savings += time_savings

            # 按任务类型分组统计
            if task_type not in breakdown:
                breakdown[task_type] = {"count": 0, "savings": 0}
            breakdown[task_type]["count"] += 1
            breakdown[task_type]["savings"] += time_savings

        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message="获取成功",
            data={
                "total_savings_minutes": total_savings,
                "total_savings_formatted": format_savings(total_savings),
                "task_count": len(completed_tasks),
                "breakdown": breakdown
            }
        ).model_dump())

    except Exception as e:
        logger.error(f"获取时间节约失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            data=None
        ).model_dump(), status=500)