# -*- coding: utf-8 -*-
"""微信公众号连接器 - 支持文章提取和监控"""

import asyncio
from enum import Enum
from agentbay.browser.browser_agent import ActOptions
from typing import Dict, Any, List, Optional
from typing import Optional, List
from playwright.async_api import Page

from .base import BaseConnector
from utils.logger import logger
from pydantic import BaseModel, Field
from models.connectors import PlatformType


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
        super().__init__(platform_name=PlatformType.WECHAT)

    async def extract_summary(
        self,
        urls: List[str],
        concurrency: int = 1
    ):
        """流式提取微信公众号文章摘要，支持并发"""
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

                        logger.info(f"[wechat] Extracted summary for URL {idx}/{len(urls)}, success={ok}")

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
    
    def _get_note_detail_config(self) -> Dict[str, Any]:
        """获取微信文章详情快速提取的配置"""
        return {
            "title_selectors": [
                "#activity-name",
                ".rich_media_title",
                "h1",
                "[id*='title']",
                ".rich_media_meta_list"
            ],
            "author_selectors": [
                "#profileBt",
                ".rich_media_meta_text",
                "[id*='author']",
                ".rich_media_meta_nickname"
            ],
            "time_selectors": [
                "#publish_time",
                ".rich_media_meta_text",
                "[id*='time']",
                ".publish-time",
                "time",
                ".rich_media_meta_list .rich_media_meta_text"
            ],
            "content_selectors": [
                "#js_content",
                ".rich_media_content",
                "[id*='content']",
                ".content"
            ],
            "image_selectors": [
                "img"
            ],
            "stats_selectors": [
                "#sg_read_num3",
                ".read_num",
                "[id*='read']",
                ".rich_media_meta_text"
            ]
        }
    
    async def get_note_detail(
        self,
        urls: List[str],
        concurrency: int = 3
    ) -> List[Dict[str, Any]]:
        """快速获取微信文章详情
        
        Args:
            urls: 文章URL列表
            concurrency: 并发数
            
        Returns:
            提取结果列表
        """
        p, browser, context = await self._get_browser_context()
        
        try:
            semaphore = asyncio.Semaphore(concurrency)
            
            async def extract_detail(url):
                async with semaphore:
                    page = None
                    try:
                        page = await context.new_page()
                        await page.goto(url, timeout=30000)
                        await page.wait_for_load_state("networkidle", timeout=10000)
                        
                        config = self._get_note_detail_config()
                        content = await self._extract_content_parallel(page, url, config)
                        
                        return {
                            "url": url,
                            "success": content.get("success", False),
                            "data": content if content.get("success") else None,
                            "error": content.get("error") if not content.get("success") else None,
                            "method": "detail_extraction"
                        }
                    except Exception as e:
                        return {
                            "url": url,
                            "success": False,
                            "error": str(e),
                            "method": "detail_extraction"
                        }
                    finally:
                        if page:
                            await page.close()
            
            tasks = [extract_detail(url) for url in urls]
            results = await asyncio.gather(*tasks)
            
        finally:
            await browser.close()
            await p.stop()
        
        return results
    
    async def extract_by_creator_id(
        self,
        creator_id: str,
        limit: Optional[int] = None,
        extract_details: bool = False
    ) -> List[Dict[str, Any]]:
        """通过公众号ID提取文章
        
        Args:
            creator_id: 公众号的 __biz 参数
            limit: 限制数量
            extract_details: 是否提取详情
            
        Returns:
            文章列表
        """
        logger.info(f"[wechat] Extracting articles from creator: {creator_id}, limit={limit}")
        
        gzh_url = f"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz={creator_id}"
        
        p, browser, context = await self._get_browser_context()
        
        try:
            page = await context.new_page()
            await page.goto(gzh_url, timeout=60000)
            await asyncio.sleep(3)
            
            instruction = "提取公众号的所有文章列表，包括：标题、链接、发布时间、阅读量、简介"
            ok, data = await self._extract_page_content(page, instruction)
            
            if ok and data:
                articles = data if isinstance(data, list) else [data]
                articles = articles[:limit] if limit else articles
                
                if extract_details:
                    # 提取每篇文章的详情
                    urls = [article.get("url", "") for article in articles if article.get("url")]
                    details = await self.get_note_detail(urls, concurrency=2)
                    
                    # 合并信息
                    results = []
                    for article, detail in zip(articles, details):
                        if detail.get("success"):
                            results.append({
                                "success": True,
                                "data": {
                                    **article,
                                    "detail": detail.get("data")
                                }
                            })
                        else:
                            results.append({
                                "success": False,
                                "error": detail.get("error"),
                                "article_info": article
                            })
                    
                    return results
                else:
                    return [{
                        "success": True,
                        "data": article
                    } for article in articles]
            
            return []
            
        finally:
            await browser.close()
            await p.stop()
    
    async def get_note_detail_single(
        self,
        url: str
    ) -> Dict[str, Any]:
        """获取单篇文章详情
        
        Args:
            url: 文章URL
            
        Returns:
            文章详情
        """
        results = await self.get_note_detail([url])
        return results[0] if results else {"success": False, "error": "No result"}
    
    async def search_and_extract(
        self,
        keyword: str,
        limit: int = 20,
        extract_details: bool = False
    ) -> List[Dict[str, Any]]:
        """搜索并提取微信文章
        
        Args:
            keyword: 搜索关键词
            limit: 限制数量
            extract_details: 是否提取详情
            
        Returns:
            搜索结果
        """
        logger.info(f"[wechat] Searching for: {keyword}")
        
        # 微信文章搜索接口（这里需要根据实际搜索页面实现）
        search_url = f"https://weixin.sogou.com/weixin?type=2&query={keyword}"
        
        p, browser, context = await self._get_browser_context()
        
        try:
            page = await context.new_page()
            await page.goto(search_url, timeout=60000)
            await asyncio.sleep(3)
            
            # 提取搜索结果
            instruction = "提取搜索结果中的文章列表，包括：标题、作者、链接、时间、摘要"
            ok, data = await self._extract_page_content(page, instruction)
            
            if ok and data:
                articles = data if isinstance(data, list) else [data]
                articles = articles[:limit] if limit else articles
                
                if extract_details:
                    # 提取每篇文章的详情
                    urls = [article.get("url", "") for article in articles if article.get("url")]
                    details = await self.get_note_detail(urls, concurrency=2)
                    
                    # 合并信息
                    results = []
                    for article, detail in zip(articles, details):
                        if detail.get("success"):
                            results.append({
                                "success": True,
                                "data": {
                                    **article,
                                    "detail": detail.get("data")
                                }
                            })
                        else:
                            results.append({
                                "success": False,
                                "error": detail.get("error"),
                                "article_info": article
                            })
                    
                    return results
                else:
                    return [{
                        "success": True,
                        "data": article
                    } for article in articles]
            
            return []
            
        finally:
            await browser.close()
            await p.stop()
