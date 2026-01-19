# -*- coding: utf-8 -*-
"""抖音连接器 - 使用 session + browser + agent 方式"""

import asyncio
import json
import time
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from bs4 import BeautifulSoup

from .base import BaseConnector
from utils.logger import logger
from utils.oss import oss_client
from agentbay import ActOptions, ExtractOptions, CreateSessionParams, BrowserContext, BrowserOption, BrowserScreen, BrowserFingerprint
from models.connectors import PlatformType

class CheckLoginStatus(BaseModel):
    """搜索结果模型"""
    has_login: bool = Field(description="是否已经登陆")

class SearchItems(BaseModel):
    """搜索结果模型"""
    title: str = Field(description="视频标题")
    url: str = Field(description="视频跳转链接")
    author: str = Field(description="作者昵称")
    liked_count: str = Field(description="点赞数")

class SearchResult(BaseModel):
    items: List[SearchItems] = Field(description="条目列表")

class CreatorsItems(BaseModel):
    """搜索结果模型"""
    user_id: str = Field(description="抖音号")
    author: str = Field(description="作者昵称")
    fans_count: int = Field(description="粉丝数,单位(个)")
    url: str = Field(description="用户主页地址")

class CreatorsResult(BaseModel):
    """搜索结果模型"""
    items: List[CreatorsItems] = Field(description="条目列表")

class VideoDetail(BaseModel):
    """视频详情模型"""
    title: str = Field(description="视频标题")
    description: str = Field(description="视频描述")
    author: str = Field(description="作者昵称")
    liked_count: str = Field(description="点赞数")
    comment_count: str = Field(description="评论数")
    share_count: str = Field(description="分享数")
    repost_count: str = Field(description="转发数")


class DouyinConnector(BaseConnector):
    """抖音连接器 - 使用 AgentBay session + browser + agent"""

    # 类变量，所有实例共享
    _login_tasks = {}

    def __init__(self, playwright):
        super().__init__(platform_name=PlatformType.DOUYIN, playwright=playwright)

    async def search_and_extract(
        self,
        keywords: List[str],
        limit: int = 20,
        user_id: Optional[str] = None,
        source: str = "default",
        source_id: str = "default",
        concurrency: int = 2
    ) -> List[Dict[str, Any]]:
        """批量搜索抖音视频（改进版：去掉 AI 视觉，直接解析 HTML）

        Args:
            keywords: 搜索关键词列表
            limit: 每个关键词限制结果数量
            user_id: 可选的用户ID过滤
            source: 来源标识
            source_id: 来源ID
            concurrency: 并发数

        Returns:
            List[Dict]: 搜索结果列表
        """

        # 使用上下文管理器（需要 CDP，使用 Playwright API）
        async with self.with_session(source, source_id, connect_cdp=True) as (session, browser, context):

            async def _process(keyword: str, idx: int):
                """处理单个关键词搜索"""
                logger.info(f"[douyin] Searching keyword {idx + 1}/{len(keywords)}: {keyword}")

                try:
                    # 1. 修正 URL：使用正确的搜索格式
                    search_url = f"https://www.douyin.com/search/{keyword}?type=video"
                    logger.info(f"[douyin] Navigating to: {search_url}")

                    # 2. 创建新页面并导航
                    page = await context.new_page()
                    try:
                        await page.goto(search_url, timeout=60000, wait_until="domcontentloaded")

                        # 3. 增加等待时间，让页面完全加载
                        await asyncio.sleep(5)

                        # 4. 滚动加载更多内容
                        scroll_count = 5
                        for i in range(scroll_count):
                            try:
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                await asyncio.sleep(2)
                                logger.info(f"[douyin] Scrolled {i + 1}/{scroll_count} times")
                            except Exception as e:
                                logger.warning(f"[douyin] Scroll failed at step {i + 1}: {e}")
                                break

                        # 5. 获取页面 HTML 内容
                        page_content = await page.content()
                        soup = BeautifulSoup(page_content, 'html.parser')
                        logger.info(f"[douyin] Page loaded, HTML length: {len(page_content)}")

                        # 6. 使用 CSS 选择器直接提取视频数据
                        videos_data = self._parse_search_videos(soup, limit, user_id)

                        if videos_data:
                            logger.info(f"[douyin] Found {len(videos_data)} videos for '{keyword}'")
                            return {
                                "keyword": keyword,
                                "success": True,
                                "data": videos_data
                            }
                        else:
                            logger.warning(f"[douyin] No videos found for '{keyword}'")
                            return {
                                "keyword": keyword,
                                "success": False,
                                "error": "No videos found in search results",
                                "data": []
                            }
                    finally:
                        await page.close()

                except Exception as e:
                    logger.error(f"[douyin] Error processing keyword '{keyword}': {e}")
                    import traceback
                    logger.error(f"[douyin] Traceback: {traceback.format_exc()}")
                    return {
                        "keyword": keyword,
                        "success": False,
                        "error": str(e),
                        "data": []
                    }

            # 并发执行搜索
            semaphore = asyncio.Semaphore(concurrency)

            async def worker(keyword, idx):
                async with semaphore:
                    return await _process(keyword, idx)

            tasks = [asyncio.create_task(worker(kw, idx)) for idx, kw in enumerate(keywords)]
            results = await asyncio.gather(*tasks)

            return results
        # 退出上下文时自动清理 session 和 browser

    async def get_note_detail(
        self,
        urls: List[str],
        source: str = "default",
        source_id: str = "default",
        concurrency: int = 2
    ) -> List[Dict[str, Any]]:
        """批量获取抖音视频详情（使用选择器快速提取，不使用 Agent）

        Args:
            urls: 视频URL列表
            source: 来源标识
            source_id: 来源ID
            concurrency: 并发数

        Returns:
            List[Dict]: 视频详情列表
        """

        # 使用上下文管理器（需要 CDP，使用 Playwright API）
        async with self.with_session(source, source_id, connect_cdp=True) as (session, browser, context):

            async def _process(url: str, idx: int):
                """处理单个视频详情提取"""
                logger.info(f"[douyin] Extracting detail {idx + 1}/{len(urls)}: {url}")

                try:
                    # 1. 创建新页面并导航
                    page = await context.new_page()
                    try:
                        await page.goto(url, timeout=60000, wait_until="domcontentloaded")

                        # 2. 等待页面完全加载（给 JavaScript 时间执行）
                        await asyncio.sleep(2)

                        await session.browser.agent.act(
                            ActOptions(
                            action="如果页面上有弹窗，请关闭它。",
                            use_vision=True),
                            page)


                        # 3. 通过 JavaScript 直接获取 window.__RENDER_DATA__（最可靠）
                        js_data = None
                        try:
                            render_data_js = """
                            () => {
                                if (typeof window !== 'undefined' && window.__RENDER_DATA__) {
                                    return {type: 'render_data', data: window.__RENDER_DATA__};
                                        }
                                return {type: 'none'};
                            }
                            """
                            js_result = await page.evaluate(render_data_js)
                            if js_result and js_result.get('type') == 'render_data':
                                js_data = js_result
                                logger.info(f"[douyin] Found window.__RENDER_DATA__ via JS")
                        except Exception as e:
                            logger.debug(f"[douyin] JS extraction failed: {e}")

                        # 4. 获取页面 HTML 内容作为备份
                        page_content = await page.content()
                        soup = BeautifulSoup(page_content, 'html.parser')
                        logger.info(f"[douyin] Page loaded, HTML length: {len(page_content)}")

                        # 5. 优先使用 JS 数据，否则解析 HTML
                        video_data = self._parse_video_detail(soup, js_data)

                        if video_data:
                            logger.info(f"[douyin] Successfully extracted detail: {video_data.get('title', 'N/A')[:30]}")
                            return {
                                "url": url,
                                "success": True,
                                "data": video_data
                            }
                        else:
                            logger.warning(f"[douyin] Failed to extract detail for: {url}")
                            return {
                                "url": url,
                                "success": False,
                                "error": "Failed to parse video detail from HTML",
                                "data": {}
                            }
                    finally:
                        await page.close()

                except Exception as e:
                    logger.error(f"[douyin] Error processing URL '{url}': {e}")
                    import traceback
                    logger.error(f"[douyin] Traceback: {traceback.format_exc()}")
                    return {
                        "url": url,
                        "success": False,
                        "error": str(e),
                        "data": {}
                    }

            # 并发执行提取
            semaphore = asyncio.Semaphore(concurrency)

            async def worker(url, idx):
                async with semaphore:
                    return await _process(url, idx)

            tasks = [asyncio.create_task(worker(u, idx)) for idx, u in enumerate(urls)]
            results = await asyncio.gather(*tasks)

            return results
        # 退出上下文时自动清理 session 和 browser

    async def harvest_user_content(
        self,
        creator_ids: List[str],
        limit: Optional[int] = None,
        source: str = "default",
        source_id: str = "default",
        concurrency: int = 2
    ) -> List[Dict[str, Any]]:
        """批量抓取创作者的视频内容（改进版：去掉 AI 视觉，容易被反爬，直接解析 HTML）

        Args:
            creator_ids: 创作者ID或昵称列表
            limit: 每个创作者限制视频数量
            source: 来源标识
            source_id: 来源ID
            concurrency: 并发数

        Returns:
            List[Dict]: 视频列表
        """

        # 使用上下文管理器（需要 CDP，使用 Playwright API）
        async with self.with_session(source, source_id, connect_cdp=True) as (session, browser, context):

            async def _process(creator_id: str, idx: int):
                """处理单个创作者的内容提取"""
                logger.info(f"[douyin] Harvesting content {idx + 1}/{len(creator_ids)}: {creator_id}")

                try:
                    # 1. 修正 URL：使用正确的搜索格式
                    search_url = f"https://www.douyin.com/search/{creator_id}?type=user"
                    logger.info(f"[douyin] Navigating to: {search_url}")

                    # 2. 创建新页面并导航
                    page = await context.new_page()
                    try:
                        await page.goto(search_url, timeout=60000, wait_until="domcontentloaded")

                        # 3. 增加等待时间，让页面完全加载
                        await asyncio.sleep(5)

                        # 4. 滚动加载更多内容（模拟真实用户行为）
                        scroll_count = 5
                        for i in range(scroll_count):
                            try:
                                # 使用 JavaScript 滚动到底部
                                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                                # 每次滚动后等待 2 秒
                                await asyncio.sleep(2)
                                logger.info(f"[douyin] Scrolled {i + 1}/{scroll_count} times")
                            except Exception as e:
                                logger.warning(f"[douyin] Scroll failed at step {i + 1}: {e}")
                                break

                        # 5. 获取页面 HTML 内容
                        page_content = await page.content()
                        soup = BeautifulSoup(page_content, 'html.parser')
                        logger.info(f"[douyin] Page loaded, HTML length: {len(page_content)}")

                        # 6. 使用 CSS 选择器直接提取用户数据
                        users_data = self._parse_search_users(soup, limit)

                        if users_data:
                            logger.info(f"[douyin] Found {len(users_data)} users for '{creator_id}'")
                            return {
                                "creator_id": creator_id,
                                "success": True,
                                "data": users_data
                            }
                        else:
                            logger.warning(f"[douyin] No users found for '{creator_id}'")
                            return {
                                "creator_id": creator_id,
                                "success": False,
                                "error": "No users found in search results",
                                "data": []
                            }
                    finally:
                        await page.close()

                except Exception as e:
                    logger.error(f"[douyin] Error harvesting from '{creator_id}': {e}")
                    import traceback
                    logger.error(f"[douyin] Traceback: {traceback.format_exc()}")
                    return {
                        "creator_id": creator_id,
                        "success": False,
                        "error": str(e),
                        "data": []
                    }

            # 并发执行采收
            semaphore = asyncio.Semaphore(concurrency)

            async def worker(creator_id, idx):
                async with semaphore:
                    return await _process(creator_id, idx)

            tasks = [asyncio.create_task(worker(cid, idx)) for idx, cid in enumerate(creator_ids)]
            results = await asyncio.gather(*tasks)

            return results
        # 退出上下文时自动清理 session 和 browser

    async def login_with_cookies(
        self,
        cookies: Dict[str, str],
        source: str = "default",
        source_id: str = "default"
    ) -> str:
        """使用 Cookie 登录抖音"""
        context_key = self._build_context_id(source, source_id)
        logger.info(f"[douyin] Logging in with context_id: {context_key}")

        # 获取或创建 Context
        context_res = await self.agent_bay.context.get(context_key, create=True)
        if not context_res.success:
            raise ValueError(f"Failed to create context: {context_res.error_message}")

        # 创建临时 Session 进行 Cookie 注入
        session_res = await self.agent_bay.create(
            CreateSessionParams(
                image_id="browser_latest",
                browser_context=BrowserContext(context_res.context.id, auto_upload=True)
            )
        )
        if not session_res.success:
            raise ValueError(f"Failed to create session: {session_res.error_message}")

        session = session_res.session
        browser = None

        try:
            await session.browser.initialize(BrowserOption(
                screen=BrowserScreen(width=1920, height=1080),
                solve_captchas=True,
                use_stealth=True,
                fingerprint=BrowserFingerprint(
                    devices=["desktop"],
                    operating_systems=["windows"],
                    locales=self.get_locale(),
                ),
            ))
            browser, context_p = await self._connect_cdp(session)
            page = await context_p.new_page()

            # 转换并注入 Cookies
            cookies_list = [{
                "name": k, "value": v, "domain": ".douyin.com", "path": "/",
                "httpOnly": False, "secure": False, "expires": int(time.time()) + 86400
            } for k, v in cookies.items()]

            await context_p.add_cookies(cookies_list)
            await asyncio.sleep(0.5)

            # 验证登录
            await page.goto("https://www.douyin.com", timeout=60000)
            await asyncio.sleep(1)

            # 检查登录状态
            is_logged_in = await self._check_login_status_douyin(page)
            logger.info(f"[douyin] Login status: {is_logged_in}")

            if not is_logged_in:
                raise ValueError("Login failed: cookies invalid or expired")

            return context_res.context.id

        finally:
            await self.cleanup_resources(session, browser)

    async def _check_login_status_douyin(self, page) -> bool:
        """检查抖音登录状态"""
        try:
            # 检查是否有用户头像等登录标识
            await page.wait_for_selector(".login-btn", timeout=3000)
            # 如果找到登录按钮，说明未登录
            return False
        except:
            # 如果没找到登录按钮，说明已登录
            return True

    async def login_with_qrcode(
        self,
        source: str = "default",
        source_id: str = "default",
        timeout: int = 120
    ) -> Dict[str, Any]:
        """二维码登录抖音

        Args:
            source: 来源标识
            source_id: 来源ID
            timeout: 超时时间（秒）

        Returns:
            Dict: 包含二维码图片 URL 的字典
        """
        context_key = self._build_context_id(source, source_id)
        logger.info(f"[douyin] QRCode login with context_id: {context_key}")

        # 创建持久化 context
        context_result = await self.agent_bay.context.get(context_key, create=True)
        if not context_result.success:
            raise ValueError(f"Failed to create context: {context_result.error_message}")

        # 创建 session（auto_upload=False，手动控制落盘时机）
        session_result = await self.agent_bay.create(
            CreateSessionParams(
                image_id="browser_latest",
                browser_context=BrowserContext(context_result.context.id, auto_upload=False)
            )
        )

        if not session_result.success:
            raise ValueError(f"Failed to create session: {session_result.error_message}")

        session = session_result.session

        try:
            # 初始化浏览器
            ok = await session.browser.initialize(BrowserOption(
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
                raise RuntimeError("Failed to initialize browser")

            # 导航到抖音登录页
            await session.browser.agent.navigate("https://www.douyin.com")
            await asyncio.sleep(1.5)

            # 检查是否已登录
            extract_options = ExtractOptions(
                instruction="""查看此页面，判断用户是否已经登录抖音。
如果页面顶部有用户头像、昵称等个人信息，则 has_login 为 true，否则为 false。
重要：只返回 JSON 格式，不要返回其他文字说明。""",
                use_vision=True,
                schema=CheckLoginStatus
            )

            try:
                success, data = await session.browser.agent.extract(extract_options)
                if success and data.has_login:
                    return {
                        "success": True,
                        "context_id": context_key,
                        "message": "Has Logining",
                        "is_logged_in": True
                    }
            except Exception as e:
                logger.warning(f"[douyin] Failed to check login status: {e}, will continue to show QR code")
                # 检查失败时，继续显示二维码（假设未登录）
                # 不立即返回，继续执行后面的二维码显示逻辑

            # 使用 Agent 找到并点击登录方式，显示二维码
            login_act = ActOptions(
                action="""
                1. 查找页面上的"登录"按钮并点击
                2. 在弹出的登录框中，选择"扫码登录"或"二维码登录"方式
                3. 确保二维码已显示在页面上
                """,
                use_vision=True
            )

            await session.browser.agent.act(login_act)
            await asyncio.sleep(2)

            # 获取二维码图片 URL
            qrcode_url = session.resource_url

            if not qrcode_url:
                raise ValueError("Failed to get QR code URL")

            logger.info(f"[douyin] QRCode generated, waiting for scan...")

            # 🔥 关键：启动后台任务，监听登录确认 + 自动落盘
            asyncio.create_task(
                self._monitor_and_cleanup(
                    session=session,
                    context_id=context_key,
                    timeout=timeout
                )
            )

            return {
                "success": True,
                "context_id": context_key,
                "browser_url": qrcode_url,  # 云浏览器 URL
                "qrcode": qrcode_url,  # 兼容旧字段
                "timeout": timeout,
                "message": "Cloud browser created, waiting for login",
                "is_logged_in": False
            }

        except Exception as e:
            logger.debug(f"[douyin] Check existing context failed: {e}")
            await self.cleanup_resources(session, None)
            await self.agent_bay.delete(session, sync_context=False)

    def _parse_search_users(self, soup: BeautifulSoup, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """从搜索页面解析用户数据（使用 BeautifulSoup）

        Args:
            soup: BeautifulSoup 解析后的页面对象
            limit: 限制返回数量

        Returns:
            List[Dict]: 用户数据列表
        """
        users_data = []

        try:
            # 参考 undoom 的选择器，查找用户卡片
            # 尝试多个可能的选择器（抖音页面结构可能变化）
            possible_selectors = [
                "div.search-result-card > a.hY8lWHgA.poLTDMYS",  # undoom 的选择器
                "a[data-e2e='search-user-card']",
                "div[class*='user'] a[href*='/user/']",
                "li[class*='user'] a[href*='/user/']",
            ]

            user_items = []
            for selector in possible_selectors:
                items = soup.select(selector)
                if items:
                    logger.info(f"[douyin] Found {len(items)} user items with selector: {selector}")
                    user_items = items
                    break

            if not user_items:
                logger.warning("[douyin] No user items found with any selector")
                # 打印部分 HTML 用于调试
                logger.debug(f"[douyin] Page HTML preview: {str(soup)[:500]}")
                return []

            # 解析每个用户卡片
            for item in user_items[:limit] if limit else user_items:
                try:
                    user_data = self._extract_single_user(item)
                    if user_data and user_data.get('author'):  # 至少要有用户名
                        users_data.append(user_data)
                except Exception as e:
                    logger.warning(f"[douyin] Failed to extract single user: {e}")
                    continue

            logger.info(f"[douyin] Successfully parsed {len(users_data)} users")

        except Exception as e:
            logger.error(f"[douyin] Error parsing search users: {e}")

        return users_data

    def _extract_single_user(self, item) -> Optional[Dict[str, Any]]:
        """从单个用户卡片元素提取数据

        Args:
            item: BeautifulSoup 元素对象

        Returns:
            Dict: 用户数据，失败返回 None
        """
        try:
            # 提取用户名/昵称（尝试多个选择器）
            author = ""
            title_selectors = [
                "div.XQwChAbX p.v9LWb7QE span span span span span",
                "span[class*='title']",
                "div[class*='title']",
                "p[class*='name']",
            ]
            for selector in title_selectors:
                elem = item.select_one(selector)
                if elem:
                    author = elem.get_text(strip=True)
                    break

            # 提取用户链接
            url = ""
            link_elem = item.select_one('a') or item
            if link_elem and link_elem.get('href'):
                href = link_elem.get('href', '')
                if href.startswith('//'):
                    url = 'https:' + href
                elif href.startswith('/'):
                    url = 'https://www.douyin.com' + href
                else:
                    url = href

            # 提取抖音号（尝试多个选择器）
            user_id = ""
            id_selectors = [
                "span:contains('抖音号')",
                "span:contains('抖音号：')",
                "div[class*='id']",
            ]
            for selector in id_selectors:
                # BeautifulSoup 不支持 :contains，需要手动查找
                elems = item.find_all('span')
                for elem in elems:
                    text = elem.get_text(strip=True)
                    if '抖音号' in text or 'douyin_id' in text:
                        # 提取冒号后面的内容
                        if ':' in text or '：' in text:
                            parts = text.split(':') if ':' in text else text.split('：')
                            if len(parts) > 1:
                                user_id = parts[1].strip()
                                break
                if user_id:
                    break

            # 提取粉丝数
            fans_count = 0
            stats_selectors = [
                "div.jjebLXt0 span",
                "span[class*='count']",
                "span[class*='fans']",
            ]
            for selector in stats_selectors:
                elems = item.select(selector)
                for elem in elems:
                    text = elem.get_text(strip=True)
                    if '粉丝' in text or 'fans' in text.lower():
                        # 提取数字
                        import re
                        numbers = re.findall(r'[\d.]+万?|[万千]', text)
                        if numbers:
                            fans_text = numbers[0]
                            # 转换为数字
                            if '万' in fans_text:
                                fans_count = int(float(fans_text.replace('万', '')) * 10000)
                            else:
                                fans_count = int(fans_text)
                            break

            # 提取获赞数
            likes_count = 0
            for elem in item.find_all('span'):
                text = elem.get_text(strip=True)
                if '获赞' in text:
                    import re
                    numbers = re.findall(r'[\d.]+万?', text)
                    if numbers:
                        likes_text = numbers[0]
                        if '万' in likes_text:
                            likes_count = int(float(likes_text.replace('万', '')) * 10000)
                        else:
                            likes_count = int(likes_text)
                    break

            # 提取简介
            description = ""
            desc_selectors = [
                "p.Kdb5Km3i span span span span span",
                "p[class*='desc']",
                "div[class*='desc']",
            ]
            for selector in desc_selectors:
                elem = item.select_one(selector)
                if elem:
                    description = elem.get_text(strip=True)
                    break

            # 提取头像 URL
            avatar_url = ""
            avatar_elem = item.select_one('img')
            if avatar_elem and avatar_elem.get('src'):
                avatar_url = avatar_elem.get('src', '')

            return {
                'author': author,
                'user_id': user_id,
                'url': url,
                'fans_count': fans_count,
                'likes_count': likes_count,
                'description': description,
                'avatar_url': avatar_url,
            }

        except Exception as e:
            logger.warning(f"[douyin] Error extracting single user: {e}")
            return None

    def _parse_search_videos(self, soup: BeautifulSoup, limit: Optional[int] = None, user_id_filter: Optional[str] = None) -> List[Dict[str, Any]]:
        """从搜索页面解析视频数据（使用 BeautifulSoup）

        Args:
            soup: BeautifulSoup 解析后的页面对象
            limit: 限制返回数量
            user_id_filter: 可选的用户ID过滤

        Returns:
            List[Dict]: 视频数据列表
        """
        videos_data = []

        try:
            # 参考 undoom 的选择器，查找视频卡片
            possible_selectors = [
                "li.SwZLHMKk",  # undoom 的选择器
                "div[class*='video-item']",
                "li[class*='video']",
                "div[data-e2e='search-video-card']",
            ]

            video_items = []
            for selector in possible_selectors:
                items = soup.select(selector)
                if items:
                    logger.info(f"[douyin] Found {len(items)} video items with selector: {selector}")
                    video_items = items
                    break

            if not video_items:
                logger.warning("[douyin] No video items found with any selector")
                logger.debug(f"[douyin] Page HTML preview: {str(soup)[:500]}")
                return []

            # 解析每个视频卡片
            for item in video_items[:limit] if limit else video_items:
                try:
                    video_data = self._extract_single_video(item)
                    if video_data and video_data.get('title'):
                        # 如果有用户ID过滤，检查作者
                        if user_id_filter and video_data.get('author') != user_id_filter:
                            continue
                        videos_data.append(video_data)
                except Exception as e:
                    logger.warning(f"[douyin] Failed to extract single video: {e}")
                    continue

            logger.info(f"[douyin] Successfully parsed {len(videos_data)} videos")

        except Exception as e:
            logger.error(f"[douyin] Error parsing search videos: {e}")

        return videos_data

    def _extract_single_video(self, item) -> Optional[Dict[str, Any]]:
        """从单个视频卡片元素提取数据

        Args:
            item: BeautifulSoup 元素对象

        Returns:
            Dict: 视频数据，失败返回 None
        """
        try:
            # 提取标题
            title = ""
            title_selectors = [
                "div.VDYK8Xd7",
                "span[class*='title']",
                "div[class*='title']",
                "a[class*='title']",
            ]
            for selector in title_selectors:
                elem = item.select_one(selector)
                if elem:
                    title = elem.get_text(strip=True)
                    break

            # 提取视频链接
            url = ""
            link_elem = item.select_one('a.hY8lWHgA') or item.select_one('a')
            if link_elem and link_elem.get('href'):
                href = link_elem.get('href', '')
                if href.startswith('//'):
                    url = 'https:' + href
                elif href.startswith('/'):
                    url = 'https://www.douyin.com' + href
                else:
                    url = href

            # 提取作者
            author = ""
            author_selectors = [
                "span.MZNczJmS",
                "span[class*='author']",
                "a[class*='author']",
            ]
            for selector in author_selectors:
                elem = item.select_one(selector)
                if elem:
                    author = elem.get_text(strip=True)
                    break

            # 提取点赞数
            liked_count = "0"
            likes_elem = item.select_one('span.cIiU4Muu')
            if likes_elem:
                liked_count = likes_elem.get_text(strip=True)

            # 提取发布时间
            publish_time = ""
            time_elem = item.select_one('span.faDtinfi')
            if time_elem:
                publish_time = time_elem.get_text(strip=True)

            return {
                'title': title,
                'url': url,
                'author': author,
                'liked_count': liked_count,
                'publish_time': publish_time,
            }

        except Exception as e:
            logger.warning(f"[douyin] Error extracting single video: {e}")
            return None

    def _parse_video_detail(self, soup: BeautifulSoup, js_data: Optional[Dict] = None) -> Optional[Dict[str, Any]]:
        """从视频详情页面解析视频数据（改进版：支持从 script 标签中提取数据）

        Args:
            soup: BeautifulSoup 解析后的页面对象
            js_data: 可选的从页面JavaScript获取的数据

        Returns:
            Dict: 视频详情数据，失败返回 None
        """
        try:
            # 1. 优先使用直接从JavaScript获取的数据
            if js_data and js_data.get('type') != 'none':
                logger.info(f"[douyin] Using JavaScript data: {js_data.get('type')}")
                video_data = self._parse_js_data(js_data)
                if video_data:
                    return video_data

            # 2. 尝试从 script 标签中提取数据（抖音的数据通常存储在 window.__RENDER_DATA__ 中）
            video_data = self._extract_from_script_tags(soup)
            if video_data:
                return video_data

            # 3. 如果 script 标签提取失败，尝试使用 CSS 选择器从 HTML 中提取
            return self._extract_from_html(soup)

        except Exception as e:
            logger.error(f"[douyin] Error parsing video detail: {e}")
            import traceback
            logger.error(f"[douyin] Traceback: {traceback.format_exc()}")
            return None

    def _extract_from_script_tags(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """从 script 标签中提取视频数据（抖音的数据通常在 window.__RENDER_DATA__ 中）"""
        try:
            import re
            import json

            # 查找所有 script 标签
            scripts = soup.find_all('script')

            for script in scripts:
                if not script.string:
                    continue

                script_content = script.string

                # 尝试提取 window.__RENDER_DATA__
                render_data_match = re.search(r'window\.__RENDER_DATA__\s*=\s*({.*?});', script_content, re.DOTALL)
                if render_data_match:
                    try:
                        render_data = json.loads(render_data_match.group(1))
                        logger.info("[douyin] Found data in window.__RENDER_DATA__")

                        # 解析数据结构
                        data = self._parse_render_data(render_data)
                        if data:
                            return data
                    except json.JSONDecodeError as e:
                        logger.warning(f"[douyin] Failed to parse __RENDER_DATA__ JSON: {e}")
                        continue

                # 尝试提取其他可能的数据格式
                # 例如：window.SSR_RENDER_DATA, window.INITIAL_STATE 等
                ssr_match = re.search(r'window\.SSR_RENDER_DATA\s*=\s*({.*?});', script_content, re.DOTALL)
                if ssr_match:
                    try:
                        ssr_data = json.loads(ssr_match.group(1))
                        logger.info("[douyin] Found data in window.SSR_RENDER_DATA")
                        data = self._parse_render_data(ssr_data)
                        if data:
                            return data
                    except json.JSONDecodeError:
                        continue

            logger.warning("[douyin] No data found in script tags")
            return None

        except Exception as e:
            logger.error(f"[douyin] Error extracting from script tags: {e}")
            return None

    def _parse_js_data(self, js_data: dict) -> Optional[Dict[str, Any]]:
        """解析从页面JavaScript直接获取的数据"""
        try:
            if not js_data or js_data.get('type') == 'none':
                return None

            data = js_data.get('data')
            if not data:
                return None

            logger.info(f"[douyin] Parsing JavaScript data, type: {js_data.get('type')}")

            # 递归查找视频数据
            video_info = self._find_video_in_data(data)

            logger.info(f"video_info {video_info}")

            if not video_info:
                logger.warning("[douyin] Video info not found in JavaScript data")
                # 打印调试信息
                logger.debug(f"[douyin] JS data structure: {str(type(data))} - {str(data)[:200] if isinstance(data, (dict, str)) else type(data)}")
                return None

            # 提取数据
            video_id = video_info.get('aweme_id') or video_info.get('video_id') or ''

            # 标题和描述
            desc = video_info.get('desc') or ''

            # 作者信息
            author_info = video_info.get('author', {})
            author = author_info.get('nickname') or author_info.get('unique_id') or author_info.get('signature', '')

            # 统计数据
            statistics = video_info.get('statistics', {})
            liked_count = str(statistics.get('digg_count') or statistics.get('diggCount') or 0)
            comment_count = str(statistics.get('comment_count') or statistics.get('commentCount') or 0)
            share_count = str(statistics.get('share_count') or statistics.get('shareCount') or 0)
            collect_count = str(statistics.get('collect_count') or statistics.get('collectCount') or 0)

            logger.info(f"[douyin] Successfully extracted from JavaScript: video_id={video_id}, title={desc[:30] if desc else 'N/A'}")

            return {
                'video_id': video_id,
                'title': desc,
                'desc': desc,
                'author': author,
                'liked_count': liked_count,
                'comment_count': comment_count,
                'share_count': share_count,
                'collect_count': collect_count,
            }

        except Exception as e:
            logger.error(f"[douyin] Error parsing JavaScript data: {e}")
            import traceback
            logger.error(f"[douyin] Traceback: {traceback.format_exc()}")
            return None

    def _find_video_in_data(self, obj, depth=0):
        """递归查找视频数据对象"""
        if depth > 15:  # 防止无限递归
            return None

        if isinstance(obj, dict):
            # 查找包含视频信息的字典
            if 'aweme_id' in obj or 'video_id' in obj or ('desc' in obj and 'author' in obj):
                return obj

            # 递归查找
            for key, value in obj.items():
                result = self._find_video_in_data(value, depth + 1)
                if result:
                    return result

        elif isinstance(obj, list):
            for item in obj:
                result = self._find_video_in_data(item, depth + 1)
                if result:
                    return result

        return None

    def _parse_render_data(self, render_data: dict) -> Optional[Dict[str, Any]]:
        """解析从 window.__RENDER_DATA__ 中提取的数据"""
        try:
            # 抖音的数据结构可能有多层嵌套，需要递归查找
            video_info = self._find_video_in_data(render_data)

            if not video_info:
                logger.warning("[douyin] Video info not found in render data")
                return None

            # 提取数据
            video_id = video_info.get('aweme_id') or video_info.get('video_id') or ''

            # 标题和描述
            desc = video_info.get('desc') or ''

            # 作者信息
            author_info = video_info.get('author', {})
            author = author_info.get('nickname') or author_info.get('unique_id') or author_info.get('signature', '')

            # 统计数据
            statistics = video_info.get('statistics', {})
            liked_count = str(statistics.get('digg_count') or statistics.get('diggCount') or 0)
            comment_count = str(statistics.get('comment_count') or statistics.get('commentCount') or 0)
            share_count = str(statistics.get('share_count') or statistics.get('shareCount') or 0)
            collect_count = str(statistics.get('collect_count') or statistics.get('collectCount') or 0)

            logger.info(f"[douyin] Successfully extracted from script: video_id={video_id}, title={desc[:30] if desc else 'N/A'}")

            return {
                'video_id': video_id,
                'title': desc,  # 抖音的 desc 实际上就是视频标题/描述
                'desc': desc,
                'author': author,
                'liked_count': liked_count,
                'comment_count': comment_count,
                'share_count': share_count,
                'collect_count': collect_count,
            }

        except Exception as e:
            logger.error(f"[douyin] Error parsing render data: {e}")
            return None

    def _extract_from_html(self, soup: BeautifulSoup) -> Optional[Dict[str, Any]]:
        """从 HTML 元素中提取视频数据（备用方法）"""
        try:
            # 提取视频ID（尝试从 URL 或页面中获取）
            video_id = ""
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string and 'video_id' in script.string:
                    import re
                    match = re.search(r'"video_id"\s*:\s*"([^"]+)"', script.string)
                    if match:
                        video_id = match.group(1)
                        break

            # 提取视频标题/描述 - 改进的选择器
            title = ""
            desc = ""

            # 尝试更多可能的选择器
            title_selectors = [
                "h1[class*='title']",
                "div[class*='title']",
                "span[class*='desc']",
                "div[class*='desc']",
                "[data-e2e='video-desc']",
                ".video-desc",
                ".desc",
            ]
            for selector in title_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and len(text) > 0:
                        if not title:
                            title = text
                        elif not desc:
                            desc = text
                        break

            # 如果标题和描述都相同，只保留标题
            if title == desc:
                desc = ""

            # 提取作者信息 - 改进的选择器
            author = ""
            author_selectors = [
                "a[class*='author']",
                "span[class*='author']",
                "div[class*='author']",
                "a[href*='/user/']",
                "[data-e2e='video-author']",
                ".author-name",
                ".user-name",
            ]
            for selector in author_selectors:
                elem = soup.select_one(selector)
                if elem:
                    author = elem.get_text(strip=True)
                    if author and len(author) > 0:
                        break

            # 提取点赞数 - 改进的选择器
            liked_count = "0"
            like_selectors = [
                "span[class*='like']",
                "span[data-e2e='video-like-count']",
                "div[class*='like'] span",
                "[data-e2e='browse-like-count']",
            ]
            for selector in like_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and any(c.isdigit() for c in text):
                        liked_count = text
                        break

            # 提取评论数 - 改进的选择器
            comment_count = "0"
            comment_selectors = [
                "span[class*='comment']",
                "span[data-e2e='video-comment-count']",
                "div[class*='comment'] span",
                "[data-e2e='browse-comment-count']",
            ]
            for selector in comment_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and any(c.isdigit() for c in text):
                        comment_count = text
                        break

            # 提取分享数 - 改进的选择器
            share_count = "0"
            share_selectors = [
                "span[class*='share']",
                "span[data-e2e='video-share-count']",
                "div[class*='share'] span",
            ]
            for selector in share_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and any(c.isdigit() for c in text):
                        share_count = text
                        break

            # 提取收藏数 - 改进的选择器
            collect_count = "0"
            collect_selectors = [
                "span[class*='collect']",
                "span[data-e2e='video-collect-count']",
                "div[class*='collect'] span",
            ]
            for selector in collect_selectors:
                elem = soup.select_one(selector)
                if elem:
                    text = elem.get_text(strip=True)
                    if text and any(c.isdigit() for c in text):
                        collect_count = text
                        break

            # 至少要有标题或作者之一
            if not title and not author:
                logger.warning("[douyin] Video detail missing both title and author")
                return None

            logger.info(f"[douyin] Successfully extracted from HTML: title={title[:30] if title else 'N/A'}")

            return {
                'video_id': video_id,
                'title': title,
                'desc': desc,
                'author': author,
                'liked_count': liked_count,
                'comment_count': comment_count,
                'share_count': share_count,
                'collect_count': collect_count,
            }

        except Exception as e:
            logger.error(f"[douyin] Error extracting from HTML: {e}")
            import traceback
            logger.error(f"[douyin] Traceback: {traceback.format_exc()}")
            return None

