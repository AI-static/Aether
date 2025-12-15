# -*- coding: utf-8 -*-
"""连接器基类 - 提取公共逻辑"""

import asyncio
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from playwright.async_api import async_playwright, Page

from agentbay import AgentBay
from agentbay.browser.browser_agent import ExtractOptions
from agentbay.session_params import CreateSessionParams, BrowserContext
from agentbay.browser.browser import BrowserOption, BrowserScreen, BrowserFingerprint
from config.settings import global_settings
from utils.logger import logger
from pydantic import BaseModel


class BaseConnector(ABC):
    """连接器基类 - 所有平台连接器的基类"""

    def __init__(self, platform_name: str):
        """初始化连接器

        Args:
            platform_name: 平台名称，用于日志和会话标识
        """
        self.platform_name = platform_name
        self.api_key = global_settings.agentbay_api_key
        if not self.api_key:
            raise ValueError("AGENTBAY_API_KEY is required")

        self.agent_bay = AgentBay(api_key=self.api_key)
        self.session = None  # 当前会话对象
        self.session_id = None  # 当前会话ID

    async def init_session(self, session_id: Optional[str] = None) -> bool:
        """初始化浏览器会话

        Args:
            session_id: 可选的会话ID，如果不提供则自动生成

        Returns:
            bool: 初始化是否成功
        """
        try:
            # 如果已有会话，先清理
            if self.session:
                self.cleanup()

            self.session_id = session_id or f"{self.platform_name}_session_{id(self)}"

            # 创建浏览器会话
            browser_context = BrowserContext(self.session_id, auto_upload=True)
            session_result = self.agent_bay.create(
                CreateSessionParams(
                    image_id="browser_latest",
                    browser_context=browser_context
                )
            )

            if not session_result.success:
                raise RuntimeError(f"Failed to create session: {session_result.error_message}")

            self.session = session_result.session

            # 初始化浏览器
            screen_option = BrowserScreen(width=1920, height=1080)
            browser_init_options = BrowserOption(
                screen=screen_option,
                solve_captchas=True,
                use_stealth=True,
                fingerprint=BrowserFingerprint(
                    devices=["desktop"],
                    operating_systems=["windows"],
                    locales=self.get_locale(),
                ),
            )

            ok = await self.session.browser.initialize_async(browser_init_options)
            if not ok:
                raise RuntimeError("Failed to initialize browser")

            logger.info(f"[{self.platform_name}] Session initialized: {self.session_id}")
            return True

        except Exception as e:
            logger.error(f"[{self.platform_name}] Failed to initialize session: {e}")
            return False

    def get_locale(self) -> List[str]:
        """获取浏览器语言设置，子类可重写"""
        return ["zh-CN"]

    async def _ensure_session(self):
        """确保会话已初始化"""
        if not self.session:
            await self.init_session()

    async def _get_browser_context(self) -> Tuple[Any, Any, Any]:
        """获取浏览器上下文（连接到 CDP）

        Returns:
            tuple: (playwright, browser, context)
        """
        await self._ensure_session()
        endpoint_url = self.session.browser.get_endpoint_url()

        p = await async_playwright().start()
        browser = await p.chromium.connect_over_cdp(endpoint_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        return p, browser, context

    async def _create_temp_session(self):
        """创建临时浏览器会话（不保存到实例属性）

        Returns:
            tuple: (session对象, playwright实例, browser, context)
        """
        # 创建临时会话ID
        temp_session_id = f"{self.platform_name}_temp_{id(self)}_{asyncio.get_event_loop().time()}"

        # 创建浏览器会话
        browser_context = BrowserContext(temp_session_id, auto_upload=True)
        session_result = self.agent_bay.create(
            CreateSessionParams(
                image_id="browser_latest",
                browser_context=browser_context
            )
        )

        if not session_result.success:
            raise RuntimeError(f"Failed to create temp session: {session_result.error_message}")

        session = session_result.session

        # 初始化浏览器
        screen_option = BrowserScreen(width=1920, height=1080)
        browser_init_options = BrowserOption(
            screen=screen_option,
            solve_captchas=True,
            use_stealth=True,
            fingerprint=BrowserFingerprint(
                devices=["desktop"],
                operating_systems=["windows"],
                locales=self.get_locale(),
            ),
        )

        ok = await session.browser.initialize_async(browser_init_options)
        if not ok:
            raise RuntimeError("Failed to initialize browser")

        # 连接到 CDP
        endpoint_url = session.browser.get_endpoint_url()
        p = await async_playwright().start()
        browser = await p.chromium.connect_over_cdp(endpoint_url)
        context = browser.contexts[0] if browser.contexts else await browser.new_context()

        logger.info(f"[{self.platform_name}] Temp session created: {temp_session_id}")

        return session, p, browser, context



    async def _extract_page_content(
        self,
        page: Page,
        instruction: str,
        schema = None
    ) -> Tuple[bool, Any]:
        """从页面提取内容

        Args:
            page: Playwright 页面对象
            instruction: 提取指令
            schema: 可选的数据结构定义

        Returns:
            tuple: (成功标志, 提取的数据)
        """
        if not self.session:
            raise RuntimeError("Session not initialized")

        agent = self.session.browser.agent

        return await agent.extract_async(
            ExtractOptions(instruction=instruction, use_text_extract=True, schema=schema),
            page=page
        )

    # ==================== 需要子类实现的抽象方法 ====================

    @abstractmethod
    async def extract_content(
        self,
        urls: List[str]
    ) -> List[Dict[str, Any]]:
        """提取内容（子类必须实现）

        Args:
            urls: 要提取的URL列表

        Returns:
            List[Dict]: 提取结果列表
        """
        pass

    async def extract_content_stream(
        self,
        urls: List[str],
        concurrency: int = 1
    ):
        """流式提取内容，逐个返回结果（子类可选重写以优化性能）

        默认实现：调用 extract_content 并逐个 yield
        子类可以重写此方法以实现真正的流式处理和并发

        Args:
            urls: 要提取的URL列表
            concurrency: 并发数量，默认1（串行）

        Yields:
            Dict: 单个URL的提取结果
        """
        results = await self.extract_content(urls)
        for result in results:
            yield result

    async def monitor_changes(self, urls: List[str], check_interval: int = 3600):
        """监控URL变化（可选实现）

        Args:
            urls: 要监控的URL列表
            check_interval: 检查间隔（秒）

        Yields:
            Dict: 变化信息
        """
        last_snapshots = {}

        while True:
            current_results = await self.extract_content(urls)

            for result in current_results:
                if not result.get("success"):
                    continue

                url = result["url"]
                current_data = result["data"]
                previous_data = last_snapshots.get(url)

                if previous_data and self._has_changes(previous_data, current_data):
                    yield {
                        "url": url,
                        "type": "content_changed",
                        "changes": self._diff_content(previous_data, current_data),
                        "timestamp": asyncio.get_event_loop().time()
                    }

                last_snapshots[url] = current_data

            await asyncio.sleep(check_interval)

    async def harvest_user_content(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """采收用户内容（可选实现）

        Args:
            user_id: 用户ID
            limit: 限制数量

        Returns:
            List[Dict]: 内容列表
        """
        raise NotImplementedError(f"{self.platform_name} does not support harvest_user_content")

    async def publish_content(
        self,
        content: str,
        content_type: str = "text",
        images: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """发布内容（可选实现）

        Args:
            content: 内容文本
            content_type: 内容类型
            images: 图片列表
            tags: 标签列表

        Returns:
            Dict: 发布结果
        """
        raise NotImplementedError(f"{self.platform_name} does not support publish_content")

    # ==================== 辅助方法 ====================

    def _has_changes(self, old: Dict[str, Any], new: Dict[str, Any]) -> bool:
        """检查两个数据是否有变化"""
        return old != new

    def _diff_content(self, old: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """比较两个数据的差异"""
        changes = {}
        all_keys = set(old.keys()) | set(new.keys())

        for key in all_keys:
            old_val = old.get(key)
            new_val = new.get(key)
            if old_val != new_val:
                changes[key] = {
                    "old": old_val,
                    "new": new_val
                }

        return changes

    def cleanup(self):
        """清理资源"""
        if self.session:
            try:
                self.session.delete()
                logger.info(f"[{self.platform_name}] Session cleaned up: {self.session_id}")
            except Exception as e:
                logger.error(f"[{self.platform_name}] Error cleaning up session: {e}")
            finally:
                self.session = None
                self.session_id = None

    def __del__(self):
        """析构时自动清理"""
        self.cleanup()
