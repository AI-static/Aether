# -*- coding: utf-8 -*-
"""连接器基类 - 提取公共逻辑"""

import asyncio
import base64
import time
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional, Tuple
from playwright.async_api import async_playwright, Page
from contextlib import asynccontextmanager

from agentbay import AsyncAgentBay
from agentbay import ExtractOptions, CreateSessionParams, BrowserContext, BrowserOption, BrowserScreen, BrowserFingerprint
from config.settings import global_settings
from utils.logger import logger
from utils.exceptions import ContextNotFoundException, SessionCreationException, BrowserInitializationException
from utils.oss import oss_client
import re
from sanic import Sanic


class BaseConnector(ABC):
    """连接器基类 - 所有平台连接器的基类
    
    设计原则：
    - 子类负责实现 _build_session_key() 方法来拼接自己的 session key
    - 不再透传 source/source_id
    - playwright 实例由外部传入，支持独立脚本运行
    """

    def __init__(self, platform_name: str, playwright):
        """初始化连接器

        Args:
            platform_name: 平台名称，用于日志和会话标识
            playwright: Playwright 实例，如果不提供则从 Sanic app 获取
        """
        self.platform_name = platform_name
        api_key = global_settings.agentbay.api_key
        if not api_key:
            raise ValueError("AGENTBAY_API_KEY is required")
        self.agent_bay = AsyncAgentBay(api_key=api_key)
        
        # Playwright 实例管理
        self.playwright = playwright
        self._login_tasks = {}

    @property
    def platform_name_str(self) -> str:
        return self.platform_name.value

    async def _get_browser_session(
            self,
            source: str = "default",
            source_id: str = "default"
    ) -> Any:
        """获取 browser session（使用持久化 context）"""
        context_key = self._build_context_id(source, source_id)
        # 获取持久化 context
        context_result = await self.agent_bay.context.get(context_key, create=False)
        if not context_result.success or not context_result.context:
            raise ContextNotFoundException(f"Context '{context_key}' not found，请先登录")

        logger.info(f"Using context {context_key} :{context_result.context.id}")

        # 使用 context 创建 session
        session_result = await self.agent_bay.create(
            CreateSessionParams(
                image_id="browser_latest",
                browser_context=BrowserContext(context_result.context.id, auto_upload=True)
            )
        )

        if not session_result.success:
            raise SessionCreationException(f"Failed to create session: {session_result.error_message}")

        session = session_result.session

        # 初始化浏览器
        ok = await session.browser.initialize(
            BrowserOption(
                screen=BrowserScreen(width=1920, height=1080),
                solve_captchas=True,
                use_stealth=True,
                fingerprint=BrowserFingerprint(
                    devices=["desktop"],
                    operating_systems=["windows"],
                    locales=self.get_locale(),
                ),
            ))
        if not ok:
            await self.agent_bay.delete(session, sync_context=False)
            raise BrowserInitializationException("Failed to initialize browser")

        return session

    async def _connect_cdp(self, session):
        """连接 CDP 并获取 context"""
        endpoint_url = await session.browser.get_endpoint_url()
        browser = await self.playwright.chromium.connect_over_cdp(endpoint_url)
        # 通常 connect_over_cdp 会复用上下文，这里取第一个
        context = browser.contexts[0] if browser.contexts else await browser.new_context()
        return browser, context

    @asynccontextmanager
    async def with_session(self, source: str = "default", source_id: str = "default", connect_cdp: bool = False):
        """Session 上下文管理器（自动管理资源生命周期）

        使用方式：
            # 只需要 Agent（不需要 CDP）
            async with self.with_session(source, source_id) as (session, _, _):
                await session.browser.agent.navigate(url)
                await session.browser.agent.extract(...)

            # 需要 Playwright API（需要 CDP）
            async with self.with_session(source, source_id, connect_cdp=True) as (session, browser, context):
                page = await context.new_page()
                await page.goto(url)
                # ...
            # 退出上下文时自动清理资源

        Args:
            source: 系统标识
            source_id: 用户标识
            connect_cdp: 是否连接 CDP（如果需要用 Playwright API，设为 True）

        Yields:
            tuple: (session, browser, context)
                   - connect_cdp=False: (session, None, None)
                   - connect_cdp=True: (session, browser, context)
        """
        # 创建 session
        session = await self._get_browser_session(source, source_id)
        browser = None
        context = None

        try:
            # 根据需要连接 CDP
            if connect_cdp:
                browser, context = await self._connect_cdp(session)

            # 返回资源给调用者
            yield session, browser, context

        finally:
            # 无论如何都清理资源
            logger.debug(f"[{self.platform_name_str}] Cleaning up session context (connect_cdp={connect_cdp})")

            try:
                if browser:
                    # 关闭 browser
                    try:
                        cdp = await browser.new_browser_cdp_session()
                        await cdp.send('Browser.close')
                        await asyncio.sleep(0.5)  # 给一点时间让 socket 关闭
                    except:
                        pass
                    await browser.close()
                    logger.debug(f"[{self.platform_name_str}] Browser closed")

                if session:
                    # 删除 session（sync_context=True 保存 Cookie）
                    await self.agent_bay.delete(session, sync_context=True)
                    logger.debug(f"[{self.platform_name_str}] Session deleted")

            except Exception as e:
                logger.error(f"[{self.platform_name_str}] Error cleaning up session: {e}")

            logger.debug(f"[{self.platform_name_str}] Session context cleanup completed")

    async def cleanup_resources(self, session, browser):
        """统一清理资源"""

        try:
            if browser:
                # 尝试通过 CDP 关闭，更干净
                cdp = await browser.new_browser_cdp_session()
                await cdp.send('Browser.close')
                await asyncio.sleep(1)  # 给一点时间让 socket 关闭
                await browser.close()
            if session:
                # 默认 sync_context=True 以保存 Cookie 状态
                await self.agent_bay.delete(session, sync_context=True)
        except Exception:
            pass

    async def _monitor_and_cleanup(
        self,
        session,
        context_id: str,
        timeout: int = 120
    ):
        """后台任务：监听登录确认 → 落盘 cookies → 清理资源

        工作流程：
        1. 订阅 Redis Pub/Sub 频道：login_confirm:{context_id}
        2. 用户点击"我已登录"后，收到消息
        3. 调用 agent_bay.delete(session, sync_context=True) 落盘 cookies
        4. 清理 session 资源

        Args:
            session: AgentBay session 对象
            context_id: AgentBay context ID
            timeout: 超时时间（秒），超时后自动清理（不落盘）
        """
        from utils.cache import get_redis

        logger.info(f"[{self.platform_name_str}] 后台任务：监听登录确认，context_id: {context_id}")

        pubsub = None
        confirm_channel = f"login_confirm:{context_id}"

        try:
            # 创建登录确认事件
            confirm_event = asyncio.Event()

            # 订阅登录确认频道
            redis = await get_redis()
            pubsub = redis.pubsub()
            await pubsub.subscribe(confirm_channel)

            logger.info(f"[{self.platform_name_str}] 已订阅登录确认频道: {confirm_channel}")

            # 监听登录确认消息
            async def listen_confirm():
                async for message in pubsub.listen():
                    if message["type"] == "message":
                        logger.info(f"[{self.platform_name_str}] 收到登录确认消息，context_id: {context_id}")
                        confirm_event.set()
                        break

            # 启动监听任务
            listen_task = asyncio.create_task(listen_confirm())

            # 等待确认或超时
            try:
                await asyncio.wait_for(confirm_event.wait(), timeout=timeout)
                logger.info(f"[{self.platform_name_str}] ✅ 用户已确认登录，开始落盘 cookies")

                # 🔥 关键：落盘 cookies
                await self.agent_bay.delete(session, sync_context=True)
                logger.info(f"[{self.platform_name_str}] ✅ Cookies 已落盘到 context: {context_id}")

            except asyncio.TimeoutError:
                logger.warning(f"[{self.platform_name_str}] ⏰ 登录确认超时 ({timeout}s)，清理资源（不落盘）")
                await self.agent_bay.delete(session, sync_context=False)

            finally:
                listen_task.cancel()
                try:
                    await listen_task
                except asyncio.CancelledError:
                    pass

        except asyncio.CancelledError:
            logger.info(f"[{self.platform_name_str}] 后台任务被取消")
            # 取消时也尝试落盘（可能已经登录了）
            try:
                await self.agent_bay.delete(session, sync_context=True)
            except Exception as e:
                logger.error(f"[{self.platform_name_str}] 取消时落盘失败: {e}")

        except Exception as e:
            logger.error(f"[{self.platform_name_str}] 后台任务异常: {e}")
            # 异常时也尝试清理资源
            try:
                await self.agent_bay.delete(session, sync_context=False)
            except Exception:
                pass

        finally:
            # 清理 Pub/Sub 连接
            if pubsub:
                try:
                    await pubsub.unsubscribe(confirm_channel)
                    await pubsub.close()
                    logger.debug(f"[{self.platform_name_str}] Pub/Sub 连接已关闭")
                except Exception as e:
                    logger.error(f"[{self.platform_name_str}] 关闭 Pub/Sub 连接时出错: {e}")

    async def take_and_save_screenshot(
        self,
        session,
        object_name: str,
        full_page: bool = False
    ) -> Optional[str]:
        """通用截图并保存到 OSS 的方法（参考 AgentBay 官方示例）

        Args:
            session: AgentBay session 对象
            object_name: OSS 对象名称（文件路径）
            full_page: 是否截取整个页面

        Returns:
            str: OSS 公共访问 URL，如果截图失败则返回 None
        """
        try:
            # 调用 agent.screenshot() 获取 base64 字符串
            s = await session.browser.agent.screenshot(full_page=full_page)

            # 检查返回值类型
            if not isinstance(s, str):
                logger.warning(f"[{self.platform_name_str}] Screenshot failed: non-string response: {type(s)}")
                return None

            s = s.strip()

            # 检查是否是 data URL 格式
            if not s.startswith("data:"):
                logger.warning(f"[{self.platform_name_str}] Unsupported screenshot format (not data URL): {s[:32]}")
                return None

            # 解析 data URL（格式：data:image/png;base64,xxxxx）
            try:
                header, encoded = s.split(",", 1)
            except ValueError:
                logger.error(f"[{self.platform_name_str}] Invalid data URL format: {s[:100]}")
                return None

            # 检查是否是 base64 格式
            if ";base64" not in header:
                logger.warning(f"[{self.platform_name_str}] Unsupported data URL (not base64): {header[:64]}")
                return None

            # 清理 base64 字符串：移除所有空白字符
            encoded = encoded.replace('\n', '').replace('\r', '').replace(' ', '').replace('\t', '')

            # 详细日志：记录原始数据
            logger.info(f"[{self.platform_name_str}] Screenshot encoded_length={len(encoded)}, first_100={encoded[:100]}, last_10={encoded[-10:]}")

            # 解码 base64 得到 bytes
            try:
                screenshot_bytes = base64.b64decode(encoded)
            except Exception as e:
                import traceback
                logger.error(f"[{self.platform_name_str}] Failed to decode base64: {traceback.format_exc()}")
                logger.error(f"[{self.platform_name_str}] Final encoded_length={len(encoded)}, full_encoded={encoded}")
                return None

            # 检查解码后的数据
            if not screenshot_bytes:
                logger.warning(f"[{self.platform_name_str}] Decoded image is empty")
                return None

            logger.info(f"[{self.platform_name_str}] Screenshot bytes length: {len(screenshot_bytes)}")

            # 上传到 OSS
            await oss_client.upload_file(object_name=object_name, file_data=screenshot_bytes)
            url = oss_client.get_public_url(object_name)

            logger.info(f"[{self.platform_name_str}] Screenshot uploaded successfully: {url}")
            return url

        except Exception as e:
            logger.error(f"[{self.platform_name_str}] Failed to take/save screenshot: {e}")
            return None

    def get_locale(self) -> List[str]:
        """获取浏览器语言设置，子类可重写"""
        return ["zh-CN"]

    def _build_context_id(self, source: str, source_id: str) -> str:
        """构建 context_id: xiaohongshu:{source}:{source_id}"""
        return f"{self.platform_name_str}-context:{source}:{source_id}"

    def _build_session_key(self, source: str = "default", source_id: str = "default") -> str:
        """构建 session key（子类可重写）
        
        Args:
            source: 系统标识
            source_id: 用户标识
            
        Returns:
            session key 字符串
        """
        return f"{self.platform_name_str}-session:{source}:{source_id}"

    # ==================== 需要子类实现的抽象方法 ====================

    @abstractmethod
    async def get_note_detail(
        self,
        urls: List[str],
        source: str = "default",
        source_id: str = "default",
        concurrency: int = 2
    ) -> List[Dict[str, Any]]:
        """批量获取笔记/文章详情（子类必须实现）

        Args:
            urls: 要提取的URL列表
            source: 来源标识
            source_id: 来源ID
            concurrency: 并发数

        Returns:
            List[Dict]: 提取结果列表，每个元素包含 url、success、data 等字段
        """
        raise NotImplementedError(f"{self.platform_name} does not support get_note_detail")

    @abstractmethod
    async def harvest_user_content(
        self,
        creator_ids: List[str],
        limit: Optional[int] = None,
        source: str = "default",
        source_id: str = "default",
        concurrency: int = 2
    ) -> List[Dict[str, Any]]:
        """批量抓取创作者内容（子类必须实现）

        Args:
            creator_ids: 创作者ID列表
            limit: 每个创作者限制数量
            source: 来源标识
            source_id: 来源ID
            concurrency: 并发数

        Returns:
            List[Dict]: 提取结果列表，每个元素包含 creator_id、success、data 等字段
        """
        raise NotImplementedError(f"{self.platform_name} does not support harvest_user_content")

    @abstractmethod
    async def search_and_extract(
        self,
        keywords: List[str],
        limit: int = 20,
        user_id: Optional[str] = None,
        source: str = "default",
        source_id: str = "default",
        concurrency: int = 2
    ) -> List[Dict[str, Any]]:
        """批量搜索并提取内容（子类必须实现）

        Args:
            keywords: 搜索关键词列表
            limit: 每个关键词限制结果数量
            user_id: 可选的用户ID过滤
            source: 来源标识
            source_id: 来源ID
            concurrency: 并发数

        Returns:
            List[Dict]: 搜索结果列表，每个元素包含 keyword、success、data 等字段
        """
        raise NotImplementedError(f"{self.platform_name} does not support search_and_extract")

    # ==================== 可选实现的辅助方法 ====================

    async def login_with_cookies(
            self,
            cookies: Dict[str, str],
            source: str = "default",
            source_id: str = "default"
    ) -> str:
        """使用 Cookie 登录（可选实现）

        Args:
            cookies: Cookie 字典
            source: 来源标识
            source_id: 来源ID

        Returns:
            str: context_id 用于恢复登录态
        """
        raise NotImplementedError(f"{self.platform_name} does not support login_with_cookies")

    async def login_with_qrcode(
            self,
            source: str = "default",
            source_id: str = "default",
            timeout: int = 120
    ) -> Dict[str, Any]:
        """二维码登录（可选实现）

        Args:
            source: 来源标识
            source_id: 来源ID
            timeout: 超时时间（秒）

        Returns:
            Dict: 包含二维码URL等信息的字典
        """
        raise NotImplementedError(f"{self.platform_name} does not support login_with_qrcode")

    async def publish_content(
        self,
        content: str,
        content_type: str = "text",
        images: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        source: str = "default",
        source_id: str = "default"
    ) -> Dict[str, Any]:
        """发布内容（可选实现）

        Args:
            content: 内容文本
            content_type: 内容类型
            images: 图片列表
            tags: 标签列表
            source: 来源标识
            source_id: 来源ID

        Returns:
            Dict: 发布结果
        """
        raise NotImplementedError(f"{self.platform_name} does not support publish_content")