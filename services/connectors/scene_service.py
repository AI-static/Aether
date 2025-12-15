"""
连接器服务层 - 统一的连接器管理和调度

提供四大核心功能：
- 监控 (monitor): 持续追踪URL变化，实时推送更新
- 提取 (extract): 一次性获取指定URL的内容
- 采收 (harvest): 批量获取用户/账号的所有内容
- 发布 (publish): 发布内容到指定平台
"""

from typing import Dict, Any, List, Optional, AsyncGenerator

from .xiaohongshu import XiaohongshuConnector
from .wechat import WechatConnector
from .generic import GenericConnector
from utils.logger import logger


class ConnectorService:
    """连接器服务 - 统一的连接器管理和调度中心"""

    # 平台标识映射
    PLATFORM_IDENTIFIERS = {
        "xiaohongshu": ["xiaohongshu.com", "xhslink.com"],
        "wechat": ["mp.weixin.qq.com"],
    }

    def __init__(self):
        """初始化连接器服务"""
        self._connectors = {}
        logger.info("[ConnectorService] Initialized")

    def _get_connector(self, platform: str):
        """获取或创建平台连接器

        Args:
            platform: 平台名称 (xiaohongshu/wechat/generic)

        Returns:
            对应的连接器实例

        Raises:
            ValueError: 不支持的平台
        """
        if platform not in self._connectors:
            if platform == "xiaohongshu":
                self._connectors[platform] = XiaohongshuConnector()
            elif platform == "wechat":
                self._connectors[platform] = WechatConnector()
            elif platform == "generic":
                self._connectors[platform] = GenericConnector()
            else:
                raise ValueError(f"不支持的平台: {platform}")

            logger.info(f"[ConnectorService] Created {platform} connector")

        return self._connectors[platform]

    def _detect_platform(self, url: str) -> str:
        """自动检测URL所属平台

        Args:
            url: 网址

        Returns:
            平台名称
        """
        for platform, identifiers in self.PLATFORM_IDENTIFIERS.items():
            if any(identifier in url for identifier in identifiers):
                return platform

        return "generic"

    def _group_urls_by_platform(self, urls: List[str]) -> Dict[str, List[str]]:
        """按平台分组URL

        Args:
            urls: URL列表

        Returns:
            平台 -> URL列表的字典
        """
        groups = {}
        for url in urls:
            platform = self._detect_platform(url)
            if platform not in groups:
                groups[platform] = []
            groups[platform].append(url)

        logger.debug(f"[ConnectorService] Grouped URLs: {dict((k, len(v)) for k, v in groups.items())}")
        return groups

    # ==================== 核心 API ====================

    async def monitor_urls(
        self,
        urls: List[str],
        platform: Optional[str] = None,
        check_interval: int = 3600,
        webhook_url: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """监控URL变化，实时推送更新

        Args:
            urls: 要监控的URL列表
            platform: 平台名称，如不指定则自动检测
            check_interval: 检查间隔（秒），默认1小时
            webhook_url: 可选的 webhook 回调地址

        Yields:
            变化事件字典，包含 url、type、changes、timestamp 等字段
        """
        try:
            if platform:
                # 指定平台
                connector = self._get_connector(platform)
                await connector.init_session()
                logger.info(f"[ConnectorService] Start monitoring {len(urls)} URLs on {platform}")

                async for change in connector.monitor_changes(urls, check_interval):
                    yield change
            else:
                # 自动检测并分组
                platform_urls = self._group_urls_by_platform(urls)
                logger.info(f"[ConnectorService] Start monitoring across {len(platform_urls)} platforms")

                for pf, url_list in platform_urls.items():
                    connector = self._get_connector(pf)
                    await connector.init_session()

                    async for change in connector.monitor_changes(url_list, check_interval):
                        yield change

        except Exception as e:
            logger.error(f"[ConnectorService] Monitor error: {e}")
            raise

    async def extract_urls(
        self,
        urls: List[str],
        platform: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """提取URL内容

        Args:
            urls: 要提取的URL列表
            platform: 平台名称，如不指定则自动检测

        Returns:
            提取结果列表，每个元素包含 url、success、data 等字段
        """
        try:
            results = []

            if platform:
                # 指定平台
                connector = self._get_connector(platform)
                logger.info(f"[ConnectorService] Extracting {len(urls)} URLs from {platform}")
                result = await connector.extract_content(urls)
                results.extend(result)
            else:
                # 自动检测并分组
                platform_urls = self._group_urls_by_platform(urls)
                logger.info(f"[ConnectorService] Extracting {len(urls)} URLs across {len(platform_urls)} platforms")

                for pf, url_list in platform_urls.items():
                    connector = self._get_connector(pf)
                    result = await connector.extract_content(url_list)
                    results.extend(result)

            success_count = sum(1 for r in results if r.get("success"))
            logger.info(f"[ConnectorService] Extraction completed: {success_count}/{len(results)} successful")

            return results

        except Exception as e:
            logger.error(f"[ConnectorService] Extract error: {e}")
            raise

    async def extract_urls_stream(
        self,
        urls: List[str],
        platform: Optional[str] = None,
        concurrency: int = 1
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """流式提取URL内容，逐个返回结果

        Args:
            urls: 要提取的URL列表
            platform: 平台名称，如不指定则自动检测
            concurrency: 并发数量，默认1（串行）

        Yields:
            单个URL的提取结果字典，包含 url、success、data 等字段
        """
        try:
            if platform:
                # 指定平台
                connector = self._get_connector(platform)
                logger.info(f"[ConnectorService] Streaming extract {len(urls)} URLs from {platform} with concurrency={concurrency}")

                async for result in connector.extract_content_stream(urls, concurrency=concurrency):
                    yield result
            else:
                # 自动检测并分组
                platform_urls = self._group_urls_by_platform(urls)
                logger.info(f"[ConnectorService] Streaming extract {len(urls)} URLs across {len(platform_urls)} platforms with concurrency={concurrency}")

                for pf, url_list in platform_urls.items():
                    connector = self._get_connector(pf)

                    async for result in connector.extract_content_stream(url_list, concurrency=concurrency):
                        yield result

        except Exception as e:
            logger.error(f"[ConnectorService] Stream extract error: {e}")
            raise

    async def harvest_user_content(
        self,
        platform: str,
        user_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """采收用户/账号的所有内容

        Args:
            platform: 平台名称
            user_id: 用户ID或账号标识
            limit: 限制数量

        Returns:
            内容列表
        """
        try:
            connector = self._get_connector(platform)
            logger.info(f"[ConnectorService] Harvesting user content from {platform}, user={user_id}, limit={limit}")

            result = await connector.harvest_user_content(user_id, limit)

            logger.info(f"[ConnectorService] Harvested {len(result)} items")
            return result

        except NotImplementedError:
            logger.error(f"[ConnectorService] Platform {platform} does not support harvest")
            raise ValueError(f"平台 {platform} 不支持采收功能")
        except Exception as e:
            logger.error(f"[ConnectorService] Harvest error: {e}")
            raise

    async def publish_content(
        self,
        platform: str,
        content: str,
        content_type: str = "text",
        images: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """发布内容到平台

        Args:
            platform: 平台名称
            content: 内容文本
            content_type: 内容类型 (text/image/video)
            images: 图片URL列表
            tags: 标签列表
            session_id: 可选的会话ID，用于复用已登录会话

        Returns:
            发布结果字典，包含 success、platform 等字段
        """
        try:
            connector = self._get_connector(platform)
            logger.info(f"[ConnectorService] Publishing content to {platform}, type={content_type}")

            if session_id:
                await connector.init_session(session_id)
            else:
                await connector.init_session()

            result = await connector.publish_content(content, content_type, images, tags)

            status = "successful" if result.get("success") else "failed"
            logger.info(f"[ConnectorService] Publish {status}")

            return result

        except NotImplementedError:
            logger.error(f"[ConnectorService] Platform {platform} does not support publish")
            raise ValueError(f"平台 {platform} 不支持发布功能")
        except Exception as e:
            logger.error(f"[ConnectorService] Publish error: {e}")
            raise

    async def login(
        self,
        platform: str,
        method: str = "cookie",
        session_id: Optional[str] = None,
        **kwargs
    ) -> bool:
        """登录平台

        Args:
            platform: 平台名称
            method: 登录方法 (目前仅支持 cookie)
            session_id: 可选的会话ID
            **kwargs: 登录参数，例如 cookies

        Returns:
            是否登录成功
        """
        try:
            if platform == "xiaohongshu" and method == "cookie":
                connector = self._get_connector(platform)
                await connector.init_session(session_id)

                cookies = kwargs.get("cookies", {})
                if not cookies:
                    raise ValueError("Cookie 登录需要提供 cookies 参数")

                logger.info(f"[ConnectorService] Logging in to {platform} with cookies")
                success = await connector.login_with_cookies(cookies)

                status = "successful" if success else "failed"
                logger.info(f"[ConnectorService] Login {status}")

                return success
            else:
                raise ValueError(f"不支持的登录方式: platform={platform}, method={method}")

        except Exception as e:
            logger.error(f"[ConnectorService] Login error: {e}")
            raise

    def cleanup(self):
        """清理所有连接器资源"""
        logger.info("[ConnectorService] Cleaning up all connectors")
        for platform, connector in self._connectors.items():
            try:
                connector.cleanup()
            except Exception as e:
                logger.error(f"[ConnectorService] Error cleaning up {platform}: {e}")

        self._connectors.clear()

    def __del__(self):
        """析构时自动清理"""
        self.cleanup()


# 全局服务实例
connector_service = ConnectorService()
