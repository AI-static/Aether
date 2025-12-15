# -*- coding: utf-8 -*-
"""小红书连接器 - 支持登录、提取、发布、监控"""

import asyncio
from typing import Dict, Any, List, Optional

from .base import BaseConnector
from utils.logger import logger
from agentbay.browser.browser_agent import ActOptions


class XiaohongshuConnector(BaseConnector):
    """小红书连接器"""

    def __init__(self):
        super().__init__(platform_name="xiaohongshu")

    async def extract_content(
        self,
        urls: List[str]
    ) -> List[Dict[str, Any]]:
        """提取小红书内容"""
        results = []
        async for result in self.extract_content_stream(urls):
            results.append(result)
        return results

    async def extract_content_stream(
        self,
        urls: List[str],
        concurrency: int = 1
    ):
        """流式提取小红书内容，支持并发"""
        # 初始化一次 session 和 browser context，所有 URL 共享
        p, browser, context = await self._get_browser_context()

        try:
            # 创建信号量来限制并发数
            semaphore = asyncio.Semaphore(concurrency)

            async def extract_single_url(url: str, idx: int):
                """提取单个 URL（使用共享的 browser context）"""
                async with semaphore:
                    logger.info(f"[xiaohongshu] Processing URL {idx}/{len(urls)}: {url}")

                    page = None
                    try:
                        # 在共享的 context 中创建新 page
                        page = await context.new_page()
                        await page.goto(url, timeout=60000)
                        await asyncio.sleep(2)

                        # 根据URL类型选择提取策略
                        if "/explore/" in url:
                            data = await self._extract_note_detail(page)
                        elif "/user/profile/" in url:
                            data = await self._extract_user_notes(page)
                        else:
                            data = await self._extract_general(page)

                        result = {
                            "url": url,
                            "success": True,
                            "data": data
                        }

                        logger.info(f"[xiaohongshu] Extracted URL {idx}/{len(urls)}")

                        return result

                    except Exception as e:
                        logger.error(f"[xiaohongshu] Error extracting {url}: {e}")
                        return {
                            "url": url,
                            "success": False,
                            "error": str(e)
                        }
                    finally:
                        # 关闭 page
                        if page:
                            await page.close()

            # 启动所有任务
            tasks = [
                asyncio.create_task(extract_single_url(url, idx))
                for idx, url in enumerate(urls, 1)
            ]

            # 使用 as_completed 来实时返回结果（谁先完成就先返回谁）
            for completed_task in asyncio.as_completed(tasks):
                result = await completed_task
                yield result

        finally:
            # 所有 URL 处理完后关闭 browser
            await browser.close()
            await p.stop()

    async def harvest_user_content(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """采收用户的所有笔记"""
        user_url = f"https://www.xiaohongshu.com/user/profile/{user_id}"

        p, browser, context = await self._get_browser_context()

        try:
            page = await context.new_page()
            await page.goto(user_url, timeout=60000)
            await asyncio.sleep(3)

            instruction = "提取用户的所有笔记，包括标题、内容摘要、互动数据（点赞、收藏、评论）、封面图"
            ok, data = await self._extract_page_content(page, instruction)

            if ok and data:
                notes = data if isinstance(data, list) else [data]
                return notes[:limit] if limit else notes

            return []

        finally:
            await browser.close()
            await p.stop()

    async def publish_content(
        self,
        content: str,
        content_type: str = "text",
        images: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """发布内容到小红书"""
        p, browser, context = await self._get_browser_context()

        try:
            page = await context.new_page()
            await page.goto("https://creator.xiaohongshu.com/publish/publish", timeout=60000)
            await asyncio.sleep(2)

            # 构建发布指令
            if content_type == "image" and images:
                instruction = f"发布图文笔记：内容「{content}」，上传图片：{', '.join(images)}，添加标签：{', '.join(tags or [])}"
            elif content_type == "video":
                instruction = f"发布视频笔记：内容「{content}」，添加标签：{', '.join(tags or [])}"
            else:
                instruction = f"发布文字笔记：内容「{content}」，添加标签：{', '.join(tags or [])}"

            # 执行发布操作
            agent = self.session.browser.agent
            success = await agent.act_async(
                ActOptions(action=instruction),
                page=page
            )

            return {
                "success": success,
                "content": content,
                "content_type": content_type,
                "platform": "xiaohongshu"
            }

        finally:
            await browser.close()
            await p.stop()

    async def login_with_cookies(self, cookies: Dict[str, str]) -> bool:
        """使用 Cookie 登录小红书"""
        p, browser, context = await self._get_browser_context()

        try:
            # 转换 cookies 格式
            cookies_list = [
                {
                    "name": name,
                    "value": value,
                    "domain": ".xiaohongshu.com"
                }
                for name, value in cookies.items()
            ]

            await context.add_cookies(cookies_list)

            page = await context.new_page()
            await page.goto("https://www.xiaohongshu.com", timeout=60000)
            await asyncio.sleep(3)

            # 检查是否登录成功
            is_logged_in = await self._check_login_status(page)

            logger.info(f"[xiaohongshu] Cookie login {'successful' if is_logged_in else 'failed'}")
            return is_logged_in

        finally:
            await browser.close()
            await p.stop()

    # ==================== 私有方法 ====================

    async def _extract_note_detail(
        self,
        page
    ) -> Dict[str, Any]:
        """提取笔记详情"""
        # 尝试从 __INITIAL_STATE__ 提取结构化数据
        try:
            initial_state = await page.evaluate("() => window.__INITIAL_STATE__")
            if initial_state and "note" in initial_state:
                note_detail_map = initial_state.get("note", {}).get("noteDetailMap", {})
                if note_detail_map:
                    note_id = list(note_detail_map.keys())[0]
                    detail_data = note_detail_map[note_id]
                    return self._process_note_detail(detail_data)
        except Exception as e:
            logger.debug(f"[xiaohongshu] Failed to extract from __INITIAL_STATE__: {e}")

        # 使用 Agent 提取
        instruction = "提取小红书笔记：标题、内容、作者信息、互动数据（点赞、收藏、评论、分享）、图片列表"
        schema = {
            "type": "object",
            "properties": {
                "title": {"type": "string", "description": "笔记标题"},
                "content": {"type": "string", "description": "笔记内容"},
                "author": {
                    "type": "object",
                    "properties": {
                        "user_id": {"type": "string"},
                        "nickname": {"type": "string"},
                        "avatar": {"type": "string"}
                    }
                },
                "interact_info": {
                    "type": "object",
                    "properties": {
                        "liked_count": {"type": "integer"},
                        "collected_count": {"type": "integer"},
                        "comment_count": {"type": "integer"},
                        "shared_count": {"type": "integer"}
                    }
                },
                "images": {"type": "array", "items": {"type": "string"}}
            }
        }
        ok, data = await self._extract_page_content(page, instruction, schema)

        return data if ok else {}

    async def _extract_user_notes(
        self,
        page
    ) -> List[Dict[str, Any]]:
        """提取用户笔记列表"""
        instruction = "提取用户的所有笔记，包括标题、互动数据、封面图、发布时间"
        schema = {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "cover": {"type": "string"},
                    "liked_count": {"type": "integer"},
                    "collected_count": {"type": "integer"},
                    "comment_count": {"type": "integer"},
                    "publish_time": {"type": "string"}
                }
            }
        }
        ok, data = await self._extract_page_content(page, instruction, schema)

        if ok and data:
            return data if isinstance(data, list) else [data]
        return []

    async def _extract_general(
        self,
        page
    ) -> Dict[str, Any]:
        """提取通用内容"""
        instruction = "提取页面主要内容和数据"
        ok, data = await self._extract_page_content(page, instruction)

        return data if ok else {}

    async def _check_login_status(self, page) -> bool:
        """检查是否已登录"""
        try:
            await page.wait_for_selector('[data-testid="avatar"]', timeout=5000)
            return True
        except:
            return False

    def _process_note_detail(self, detail: dict) -> dict:
        """处理笔记详情的原始数据"""
        note = detail.get("note", {})
        user = note.get("user", {})
        interact_info = note.get("interactInfo", {})
        image_list = note.get("imageList", [])

        return {
            "note_id": note.get("noteId"),
            "title": note.get("title"),
            "desc": note.get("desc"),
            "type": note.get("type"),
            "time": note.get("time"),
            "user": {
                "user_id": user.get("userId"),
                "nickname": user.get("nickname") or user.get("nickName"),
                "avatar": user.get("avatar")
            },
            "interact_info": {
                "liked_count": interact_info.get("likedCount"),
                "comment_count": interact_info.get("commentCount"),
                "shared_count": interact_info.get("sharedCount"),
                "collected_count": interact_info.get("collectedCount")
            },
            "images": [
                {
                    "url": img.get("urlDefault"),
                    "width": img.get("width"),
                    "height": img.get("height")
                }
                for img in image_list
            ]
        }
