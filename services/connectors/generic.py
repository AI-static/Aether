# -*- coding: utf-8 -*-
"""通用网站连接器 - 支持任何网站的内容提取"""

import asyncio
from typing import Dict, Any, List, Optional

from .base import BaseConnector
from utils.logger import logger


class GenericConnector(BaseConnector):
    """通用网站连接器 - 适用于任何网站"""

    def __init__(self):
        super().__init__(platform_name="generic")

    async def extract_content(
        self,
        urls: List[str]
    ) -> List[Dict[str, Any]]:
        """提取通用网站内容"""
        results = []
        async for result in self.extract_content_stream(urls):
            results.append(result)
        return results

    async def extract_content_stream(
        self,
        urls: List[str],
        concurrency: int = 1
    ):
        """流式提取通用网站内容，支持并发"""
        # 定义提取指令
        instruction = "提取网页的主要内容，包括标题、正文、重要信息和数据"

        # 初始化一次 session 和 browser context，所有 URL 共享
        p, browser, context = await self._get_browser_context()

        try:
            # 创建信号量来限制并发数
            semaphore = asyncio.Semaphore(concurrency)

            async def extract_single_url(url: str, idx: int):
                """提取单个 URL（使用共享的 browser context）"""
                async with semaphore:
                    logger.info(f"[generic] Processing URL {idx}/{len(urls)}: {url}")

                    page = None
                    try:
                        # 在共享的 context 中创建新 page
                        page = await context.new_page()
                        await page.goto(url, timeout=60000)
                        await asyncio.sleep(2)

                        # 提取内容
                        ok, data = await self._extract_page_content(page, instruction)

                        result = {
                            "url": url,
                            "success": ok,
                            "data": data if ok else {}
                        }

                        logger.info(f"[generic] Extracted URL {idx}/{len(urls)}, success={ok}")

                        return result

                    except Exception as e:
                        logger.error(f"[generic] Error extracting {url}: {e}")
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
