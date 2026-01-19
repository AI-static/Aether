# -*- coding: utf-8 -*-
"""Agent 基类 - 提供资源管理"""

from abc import ABC, abstractmethod
from typing import List, Any, Dict
from utils.logger import logger


class BaseAgent(ABC):
    """Agent 基类 - 所有 Agent 的父类

    提供功能：
    - Connector 管理（自动追踪和清理）
    - 统一的 cleanup 接口
    """

    def __init__(self, source_id: str, source: str, playwright: Any, task: Any):
        """初始化 Agent

        Args:
            source_id: 用户标识
            source: 系统标识
            playwright: Playwright 实例
            task: 任务对象
        """
        self._source_id = source_id
        self._source = source
        self._playwright = playwright
        self._task = task

        # Connector 追踪列表
        self._connectors: List[Any] = []

    def add_connector(self, connector: Any):
        """添加一个 connector 到追踪列表

        Args:
            connector: ConnectorService 实例
        """
        self._connectors.append(connector)
        logger.debug(f"[Agent] Added connector, total: {len(self._connectors)}")

    async def cleanup(self):
        """清理所有 Connector 资源

        在任务取消、完成或失败时自动调用
        """
        logger.info(f"[Agent] Cleaning up {len(self._connectors)} connectors")

        # 遍历清理所有 connector
        for connector in self._connectors:
            try:
                # 调用每个 connector 的 cleanup 方法
                if hasattr(connector, 'cleanup'):
                    await connector.cleanup()
                    logger.debug(f"[Agent] Cleaned connector")
            except Exception as e:
                logger.error(f"[Agent] Error cleaning connector: {e}")

        # 清空列表
        self._connectors.clear()

        logger.info(f"[Agent] Cleanup completed for task {self._task.id if self._task else 'unknown'}")

    async def _wait_for_login_confirmation(self, context_id: str, timeout: int = 120):
        """等待用户确认登录

        用户在前端点击"我已登录"后，会通过 Redis Pub/Sub 发送消息
        收到消息后，继续执行任务

        Args:
            context_id: AgentBay context ID
            timeout: 超时时间（秒）

        使用场景：
            Agent 检测到未登录时，调用此方法等待用户确认登录
            用户扫码并点击"我已登录"后，Agent 继续执行后续逻辑
        """
        import asyncio
        from utils.cache import get_redis

        logger.info(f"[Agent] 等待用户确认登录，context_id: {context_id}")

        pubsub = None
        confirm_channel = f"login_confirm:{context_id}"

        try:
            # 创建登录确认事件
            confirm_event = asyncio.Event()

            # 订阅登录确认频道
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(confirm_channel)

            logger.info(f"[Agent] 已订阅登录确认频道: {confirm_channel}")

            # 监听登录确认消息
            async def listen_confirm():
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        logger.info(f"[Agent] 收到登录确认消息，context_id: {context_id}")
                        confirm_event.set()
                        break

            # 启动监听任务
            listen_task = asyncio.create_task(listen_confirm())

            # 等待确认或超时
            try:
                await asyncio.wait_for(confirm_event.wait(), timeout=timeout)
                logger.info(f"[Agent] 用户已确认登录，继续执行任务")
            except asyncio.TimeoutError:
                logger.warning(f"[Agent] 登录确认超时 ({timeout}s)，继续执行任务")

            finally:
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass

        except Exception as e:
            logger.error(f"[Agent] 等待登录确认时出错: {e}")

        finally:
            # 清理 Pub/Sub 连接
            if pubsub:
                try:
                    await pubsub.unsubscribe(confirm_channel)
                    await pubsub.close()
                    logger.debug(f"[Agent] Pub/Sub 连接已关闭")
                except Exception as e:
                    logger.error(f"[Agent] 关闭 Pub/Sub 连接时出错: {e}")

    @abstractmethod
    async def execute(self, **kwargs) -> Dict[str, Any]:
        """执行 Agent 任务（子类必须实现）

        Args:
            **kwargs: Agent 参数

        Returns:
            执行结果字典
        """
        pass