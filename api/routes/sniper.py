# -*- coding: utf-8 -*-
"""Sniper API 路由 - 简化版，支持任务记录和上下文追踪"""

from sanic import Blueprint, Request
from sanic.response import json, ResponseStream
import ujson as json_lib
import asyncio

from api.schema.base import BaseResponse, ErrorCode
from services.sniper.task_service import TaskService
from utils.logger import logger

sniper_bp = Blueprint("sniper", url_prefix="/sniper")


@sniper_bp.post("/trend")
async def create_trend_task(request: Request):
    """创建趋势分析任务"""
    try:
        data = request.json
        keywords = data.get("keywords", [])
        platform = data.get("platform", "xiaohongshu")

        auth_info = request.ctx.auth_info
        task_service = TaskService(request.app.ctx.playwright)

        # 创建任务记录
        task = await task_service.create_task(
            source_id=auth_info.source_id,
            task_type="trend_analysis",
            config={
                "keywords": keywords,
                "platform": platform,
                "depth": data.get("depth", "deep")
            }
        )

        # 启动后台执行（直接调用现有 service）
        from services.sniper.xhs_trend import XiaohongshuDeepAgent
        background_task = asyncio.create_task(
            _run_trend_analysis(task, request.app.ctx.playwright)
        )
        task_service._running_tasks[str(task.id)] = background_task

        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message="任务已创建",
            data={
                "task_id": str(task.id),
                "status": task.status,
                "goal": f"分析关键词 {keywords} 的爆款趋势"
            }
        ).model_dump())

    except Exception as e:
        logger.error(f"创建任务失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            data=None
        ).model_dump(), status=500)


async def _run_trend_analysis(task, playwright):
    """后台执行趋势分析 - 记录每一步到 Task"""
    from services.sniper.xhs_trend import XiaohongshuDeepAgent
    from services.connector_service import ConnectorService
    from models.connectors import PlatformType

    try:
        await task.start()
        config = task.config
        keywords = config["keywords"]

        # Step 1: 关键词裂变
        agent = XiaohongshuDeepAgent(
            source_id=task.source_id,
            playwright=playwright,
            keywords=keywords[0] if keywords else ""
        )

        search_keywords = await agent._generate_keywords()
        await task.update_context("step_1_keywords", search_keywords)
        await task.log_step(1, "关键词裂变",
                           {"core_keyword": keywords[0]},
                           {"keywords": search_keywords})
        task.progress = 20
        await task.save()

        # Step 2: 搜索并去重
        top_notes = await agent._run_search(search_keywords, limit=config.get("limit", 50))
        await task.update_context("step_2_notes", top_notes)
        await task.log_step(2, "搜索去重",
                           {"keywords": search_keywords},
                           {"unique_count": len(top_notes)})
        task.progress = 50
        await task.save()

        # Step 3: 获取详情
        details = await agent._fetch_details(top_notes)
        await task.update_context("step_3_details", details)
        await task.log_step(3, "获取详情",
                           {"note_count": len(top_notes)},
                           {"details_count": len(details)})
        task.progress = 70
        await task.save()

        # Step 4: Agent 分析
        prompt = f"任务词: {keywords}\n数据: {details}\n请分析爆款逻辑并给出建议。"
        analysis_result = await agent.agent.arun(prompt)
        analysis = analysis_result.content
        await task.update_context("step_4_analysis", {"analysis": analysis})
        await task.log_step(4, "Agent分析",
                           {"data_size": len(details)},
                           {"analysis_length": len(analysis)})
        task.progress = 95
        await task.save()

        # 完成
        await task.complete({
            "summary": f"分析完成，共 {len(top_notes)} 篇笔记",
            "analysis": analysis,
            "keywords": search_keywords
        })

    except Exception as e:
        await task.fail(str(e), task.progress)


@sniper_bp.get("/task/<task_id:str>")
async def get_task(request: Request, task_id: str):
    """获取任务详情 - Agent 可读格式"""
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
