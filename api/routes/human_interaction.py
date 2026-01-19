# -*- coding: utf-8 -*-
"""Human-in-Loop 交互 API 路由"""

from sanic import Blueprint, Request
from sanic.response import json
from models.task import Task, TaskStatus
from models.interactions import UserConfirmRequest
from api.schema.base import BaseResponse, ErrorCode
from pydantic import ValidationError
from utils.logger import logger
from api.routes.sniper import AGENT_WORKFLOW_MAPPING, _run_agent_task
import asyncio

# 创建蓝图
human_interaction_bp = Blueprint("human_interaction", url_prefix="/interactions")


async def handle_user_confirm(task_id: str, confirm_data: UserConfirmRequest):
    """处理用户确认（内部方法）

    Args:
        task_id: 任务ID
        confirm_data: 用户确认数据

    Returns:
        BaseResponse
    """
    # 验证任务是否存在
    task = await Task.get_or_none(id=task_id)
    if not task:
        return BaseResponse(
            code=ErrorCode.NOT_FOUND,
            message="任务不存在",
            data=None
        )

    # 检查任务状态
    if task.status not in [TaskStatus.WAITING_HUMAN_INPUT]:
        return BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message=f"任务状态错误: {task.status}，无法处理确认",
            data=None
        )

    # 获取交互信息
    interaction_info = None
    if task.result and isinstance(task.result, dict):
        interaction_info = task.result.get("interaction")

    if not interaction_info:
        return BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message="任务未等待交互",
            data=None
        )

    interaction_type = interaction_info.get("interaction_type")
    logger.info(f"[Human-in-Loop] 处理用户确认: task_id={task_id}, type={interaction_type}, confirmed={confirm_data.confirmed}")

    # 根据交互类型分发处理
    if interaction_type == "login_confirm":
        return await _handle_login_confirm(task, interaction_info, confirm_data)
    elif interaction_type == "content_review":
        return await _handle_content_review(task, interaction_info, confirm_data)
    elif interaction_type == "image_select":
        return await _handle_image_select(task, interaction_info, confirm_data)
    else:
        return await _handle_custom_interaction(task, interaction_info, confirm_data)


async def _retry_task(task: Task) -> str:
    """重试任务的内部方法

    Args:
        task: 任务对象

    Returns:
        任务ID
    """
    # 重置任务状态（复用原任务对象）
    task.status = TaskStatus.RUNNING
    task.progress = 0
    task.error = None
    # 保留 result 中的 user_response，但移除 interaction
    if task.result and "user_response" in task.result:
        user_response = task.result["user_response"]
        task.result = {"user_response": user_response}
    else:
        task.result = None
    task.started_at = None
    task.completed_at = None
    # logs 保留，作为历史记录参考
    await task.save()

    # 获取 Agent 类
    agent_id = task.task_type
    if agent_id not in AGENT_WORKFLOW_MAPPING:
        raise ValueError(f"不支持的 Agent/Workflow: {agent_id}")

    agent_class = AGENT_WORKFLOW_MAPPING[agent_id]

    # 获取原参数
    original_params = task.params or {}

    # 在后台执行 Agent，复用同一个 task
    # 注意：这里需要创建一个假的 request 对象，因为 _run_agent_task 需要它
    from unittest.mock import Mock
    request = Mock(spec=Request)

    asyncio.create_task(_run_agent_task(agent_class, request, task, **original_params))

    logger.info(f"[Human-in-Loop] 任务已重试: {task.id}")
    return str(task.id)


async def _handle_login_confirm(task: Task, interaction_info: dict, confirm_data: UserConfirmRequest):
    """处理登录确认"""
    from utils.cache import get_redis

    context_id = interaction_info.get("data", {}).get("context_id")
    platform = interaction_info.get("data", {}).get("platform", "unknown")

    if not context_id:
        return BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message="缺少 context_id",
            data=None
        )

    logger.info(f"[Human-in-Loop] 登录确认: platform={platform}, context_id={context_id}")

    # 发布 Redis 消息（触发 connector 后台任务落盘 cookies）
    redis = await get_redis()
    confirm_channel = f"login_confirm:{context_id}"
    await redis.publish(confirm_channel, "confirm")
    logger.info(f"[Human-in-Loop] 已发布登录确认消息: {confirm_channel}")

    # 自动重试任务
    try:
        retry_task_id = await _retry_task(task)
    except Exception as e:
        logger.error(f"[Human-in-Loop] 重试任务失败: {e}")
        retry_task_id = None

    response_data = {
        "context_id": context_id,
        "platform": platform,
        "retry_task_id": retry_task_id
    }

    return BaseResponse(
        code=ErrorCode.SUCCESS,
        message="登录确认成功，cookies 已落盘，任务已重新执行",
        data=response_data
    )


async def _handle_content_review(task: Task, interaction_info: dict, confirm_data: UserConfirmRequest):
    """处理内容审核"""
    if confirm_data.confirmed:
        # 用户确认，继续执行
        logger.info(f"[Human-in-Loop] 内容审核通过: task_id={task.id}")

        # 自动重试任务
        try:
            retry_task_id = await _retry_task(task)
            return BaseResponse(
                code=ErrorCode.SUCCESS,
                message="审核通过，任务已继续执行",
                data={"retry_task_id": retry_task_id}
            )
        except Exception as e:
            logger.error(f"[Human-in-Loop] 重试任务失败: {e}")
            return BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message=f"重试任务失败: {e}",
                data=None
            )
    else:
        # 用户拒绝，取消任务
        logger.info(f"[Human-in-Loop] 内容审核被拒绝: task_id={task.id}, reason={confirm_data.comment}")
        await task.fail(f"内容审核被拒绝: {confirm_data.comment or '无备注'}")

        return BaseResponse(
            code=ErrorCode.SUCCESS,
            message="任务已取消",
            data={"status": "cancelled"}
        )


async def _handle_image_select(task: Task, interaction_info: dict, confirm_data: UserConfirmRequest):
    """处理图片选择"""
    selected_images = confirm_data.response_data.get("selected_images", []) if confirm_data.response_data else []

    if not selected_images:
        return BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message="未选择图片",
            data=None
        )

    logger.info(f"[Human-in-Loop] 图片选择完成: task_id={task.id}, selected={len(selected_images)}")

    # 更新任务 result，保存用户选择
    task.result = task.result or {}
    task.result["user_response"] = {
        "selected_images": selected_images
    }
    await task.save()

    # 自动重试任务
    retry_task_id = await _retry_task(task)

    return BaseResponse(
        code=ErrorCode.SUCCESS,
        message=f"已选择 {len(selected_images)} 张图片，任务已继续执行",
        data={
            "selected_count": len(selected_images),
            "retry_task_id": retry_task_id
        }
    )


async def _handle_custom_interaction(task: Task, interaction_info: dict, confirm_data: UserConfirmRequest):
    """处理自定义交互"""
    logger.info(f"[Human-in-Loop] 自定义交互: task_id={task.id}, type={interaction_info.get('interaction_type')}")

    # 保存用户响应
    task.result = task.result or {}
    task.result["user_response"] = {
        "confirmed": confirm_data.confirmed,
        "data": confirm_data.response_data,
        "comment": confirm_data.comment
    }
    await task.save()

    if confirm_data.confirmed:
        # 用户确认，重试任务
        retry_task_id = await _retry_task(task)
        return BaseResponse(
            code=ErrorCode.SUCCESS,
            message="交互已确认，任务已继续执行",
            data={"retry_task_id": retry_task_id}
        )
    else:
        # 用户拒绝，取消任务
        await task.fail(f"用户拒绝: {confirm_data.comment or '无备注'}")
        return BaseResponse(
            code=ErrorCode.SUCCESS,
            message="任务已取消",
            data={"status": "cancelled"}
        )


@human_interaction_bp.post("/<task_id>/confirm")
async def confirm_interaction(request: Request, task_id: str):
    """通用的人类交互确认接口

    处理所有类型的用户交互确认：
    - 登录确认 (login_confirm)
    - 内容审核 (content_review)
    - 图片选择 (image_select)
    - 自定义审批 (custom_approval)

    Args:
        task_id: 任务ID
        请求体: UserConfirmRequest
    """
    try:
        # 解析请求数据
        try:
            confirm_data = UserConfirmRequest(**request.json)
        except ValidationError as e:
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message=f"参数验证失败: {str(e)}",
                data=None
            ).model_dump(), status=400)

        # 处理确认
        result = await handle_user_confirm(task_id, confirm_data)

        return json(result.model_dump())

    except Exception as e:
        logger.error(f"[Human-in-Loop] 处理交互确认失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=str(e),
            data=None
        ).model_dump(), status=500)