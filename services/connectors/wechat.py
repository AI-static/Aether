# -*- coding: utf-8 -*-
"""微信公众号连接器 - 支持文章提取和监控"""

import asyncio
from enum import Enum
from agentbay.browser.browser_agent import ActOptions
from typing import Dict, Any, List, Optional
from typing import Optional, List

from .base import BaseConnector
from utils.logger import logger
from pydantic import BaseModel, Field


class ExtractType(str, Enum):
    """提取类型枚举"""
    LIST = "list"            # URL列表提取
    SEARCH = "search"        # 搜索结果提取
    AUTHOR = "author"        # 公众号历史文章


class GzhArticleSummary(BaseModel):
    """公众号文章摘要（用于URL列表详情提取）"""
    title: str = Field(..., description="文章标题")
    author: str = Field(..., description="公众号名称")
    publish_time: str = Field("", description="发布时间")
    read_count: int = Field(0, description="阅读量")
    like_count: int = Field(0, description="点赞数")
    main_point: str = Field("", description="文章核心观点")
    key_points: List[str] = Field(default_factory=list, description="关键要点列表")
    pic_urls: List[str] = Field(default_factory=list, description="图片链接")


class GzhArticleListItem(BaseModel):
    """公众号文章列表项（用于搜索和作者文章列表提取）"""
    title: str = Field(..., description="文章标题")
    author: str = Field(..., description="公众号名称")
    publish_time: str = Field("", description="发布时间")
    url: str = Field("", description="完整文章跳转链接，http开头")
    lead: str = Field("", description="文章引言或者开头")

class GzhArticleList(BaseModel):
    items: List[GzhArticleListItem] = Field(..., description="当前页面上的全部文章")


class WechatConnector(BaseConnector):
    """微信公众号连接器"""

    def __init__(self):
        super().__init__(platform_name="wechat")

    async def extract_content(
        self,
        urls: List[str]
    ) -> List[Dict[str, Any]]:
        """提取微信公众号文章内容"""
        results = []
        async for result in self.extract_content_stream(urls):
            results.append(result)
        return results

    async def extract_content_stream(
        self,
        urls: List[str],
        concurrency: int = 1
    ):
        """流式提取微信公众号文章内容，支持并发"""
        # 定义提取指令
        instruction = "提取公众号文章：标题、作者、发布时间、阅读量、点赞数、在看数、内容摘要"

        # 初始化一次 session 和 browser context，所有 URL 共享
        p, browser, context = await self._get_browser_context()

        try:
            # 创建信号量来限制并发数
            semaphore = asyncio.Semaphore(concurrency)

            async def extract_single_url(url: str, idx: int):
                """提取单个 URL（使用共享的 browser context）"""
                async with semaphore:
                    logger.info(f"[wechat] Processing URL {idx}/{len(urls)}: {url}")

                    page = None
                    try:
                        # 在共享的 context 中创建新 page
                        page = await context.new_page()
                        await page.goto(url, timeout=60000)
                        await asyncio.sleep(2)

                        # 关闭可能出现的弹窗
                        try:
                            agent = self.session.browser.agent
                            await agent.act_async(
                                ActOptions(action="如果有弹窗或广告，关闭它们，然后滑动到文章最下边。"),
                                page=page
                            )
                        except:
                            pass

                        # 提取文章内容
                        ok, data = await self._extract_page_content(page, instruction, GzhArticleSummary)

                        result = {
                            "url": url,
                            "success": ok,
                            "data": data.model_dump() if ok else {}
                        }

                        logger.info(f"[wechat] Extracted URL {idx}/{len(urls)}, success={ok}")

                        return result

                    except Exception as e:
                        logger.error(f"[wechat] Error extracting {url}: {e}")
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

    async def monitor_changes(self, urls: List[str], check_interval: int = 3600):
        """监控文章数据变化（主要是阅读量、点赞数等）"""
        last_snapshots = {}

        while True:
            current_results = await self.extract_content(urls)

            for result in current_results:
                if not result.get("success"):
                    continue

                url = result["url"]
                current_data = result["data"]
                previous_data = last_snapshots.get(url)

                if previous_data:
                    # 检查关键指标变化
                    changes = {}
                    for key in ["read_count", "like_count", "comment_count", "share_count"]:
                        old_val = previous_data.get(key)
                        new_val = current_data.get(key)
                        if old_val is not None and new_val is not None and old_val != new_val:
                            changes[key] = {
                                "old": old_val,
                                "new": new_val,
                                "diff": new_val - old_val if isinstance(new_val, (int, float)) else None
                            }

                    if changes:
                        yield {
                            "url": url,
                            "type": "stats_changed",
                            "changes": changes,
                            "timestamp": asyncio.get_event_loop().time()
                        }

                last_snapshots[url] = current_data

            await asyncio.sleep(check_interval)

    async def harvest_user_content(
        self,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """采收公众号的所有文章

        Args:
            user_id: 公众号的 __biz 参数
            limit: 限制数量
        """
        gzh_url = f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={user_id}"

        p, browser, context = await self._get_browser_context()

        try:
            page = await context.new_page()
            await page.goto(gzh_url, timeout=60000)
            await asyncio.sleep(3)

            instruction = "提取公众号的所有文章列表，包括：标题、链接、发布时间、阅读量、简介"
            ok, data = await self._extract_page_content(page, instruction)

            if ok and data:
                articles = data if isinstance(data, list) else [data]
                return articles[:limit] if limit else articles

            return []

        finally:
            await browser.close()
            await p.stop()
