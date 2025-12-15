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
from models.connectors import PlatformType, LoginMethod


class ConnectorService:
    """连接器服务 - 统一的连接器管理和调度中心"""

    # 平台标识映射
    PLATFORM_IDENTIFIERS = {
        PlatformType.XIAOHONGSHU: ["xiaohongshu.com", "xhslink.com"],
        PlatformType.WECHAT: ["mp.weixin.qq.com"],
    }

    def __init__(self):
        """初始化连接器服务"""
        self._connectors = {}
        logger.info("[ConnectorService] Initialized")

    def _get_connector(self, platform: str | PlatformType):
        """获取或创建平台连接器

        Args:
            platform: 平台名称 (xiaohongshu/wechat/generic)

        Returns:
            对应的连接器实例

        Raises:
            ValueError: 不支持的平台
        """
        # 转换为枚举类型
        if isinstance(platform, str):
            platform = PlatformType(platform)
        
        platform_key = str(platform)
        
        if platform_key not in self._connectors:
            if platform == PlatformType.XIAOHONGSHU:
                self._connectors[platform_key] = XiaohongshuConnector()
            elif platform == PlatformType.WECHAT:
                self._connectors[platform_key] = WechatConnector()
            elif platform == PlatformType.GENERIC:
                self._connectors[platform_key] = GenericConnector()
            else:
                raise ValueError(f"不支持的平台: {platform}")

            logger.info(f"[ConnectorService] Created {platform_key} connector")

        return self._connectors[platform_key]

    def _detect_platform(self, url: str) -> PlatformType:
        """自动检测URL所属平台

        Args:
            url: 网址

        Returns:
            平台名称
        """
        for platform, identifiers in self.PLATFORM_IDENTIFIERS.items():
            if any(identifier in url for identifier in identifiers):
                return platform

        return PlatformType.GENERIC

    def _group_urls_by_platform(self, urls: List[str]) -> Dict[PlatformType, List[str]]:
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

        logger.debug(f"[ConnectorService] Grouped URLs: {dict((str(k), len(v)) for k, v in groups.items())}")
        return groups

    # ==================== 核心 API ====================

    async def extract_summary(
        self,
        urls: List[str],
        platform: Optional[str] = None,
        concurrency: Optional[int] = 10,
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
                result = await connector.extract_summary(urls, concurrency)
                results.extend(result)
            else:
                # 自动检测并分组
                platform_urls = self._group_urls_by_platform(urls)
                logger.info(f"[ConnectorService] Extracting {len(urls)} URLs across {len(platform_urls)} platforms")

                for pf, url_list in platform_urls.items():
                    connector = self._get_connector(pf)
                    result = await connector.extract_summary(url_list)
                    results.extend(result)

            success_count = sum(1 for r in results if r.get("success"))
            logger.info(f"[ConnectorService] Extraction completed: {success_count}/{len(results)} successful")

            return results

        except Exception as e:
            logger.error(f"[ConnectorService] Extract error: {e}")
            raise

    async def get_note_details(
        self,
        urls: List[str],
        platform: Optional[str] = None,
        concurrency: int = 3
    ) -> List[Dict[str, Any]]:
        """获取笔记/文章详情（快速提取，不使用Agent）

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
                logger.info(f"[ConnectorService] Getting note details for {len(urls)} URLs from {platform}")

                # 调用 get_note_detail 方法
                results = await connector.get_note_detail(urls, concurrency=concurrency)
            else:
                # 自动检测并分组
                platform_urls = self._group_urls_by_platform(urls)
                logger.info(f"[ConnectorService] Getting note details for {len(urls)} URLs across {len(platform_urls)} platforms")

                for pf, url_list in platform_urls.items():
                    connector = self._get_connector(pf)
                    
                    platform_results = await connector.get_note_detail(url_list, concurrency=concurrency)
                    results.extend(platform_results)

            success_count = sum(1 for r in results if r.get("success"))
            logger.info(f"[ConnectorService] Get note details completed: {success_count}/{len(results)} successful")

            return results

        except Exception as e:
            logger.error(f"[ConnectorService] Get note details error: {e}")
            raise

    async def harvest_user_content(
        self,
        platform: str | PlatformType,
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
        platform: str | PlatformType,
        content: str,
        content_type: str = "text",
        images: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
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

    async def extract_by_creator_id(
        self,
        platform: str | PlatformType,
        creator_id: str,
        limit: Optional[int] = None,
        extract_details: bool = False
    ) -> List[Dict[str, Any]]:
        """通过创作者ID提取内容

        Args:
            platform: 平台名称
            creator_id: 创作者ID
            limit: 限制数量
            extract_details: 是否提取详情

        Returns:
            提取结果列表
        """
        try:
            connector = self._get_connector(platform)
            logger.info(f"[ConnectorService] Extracting by creator ID from {platform}, creator={creator_id}")
            
            results = await connector.extract_by_creator_id(
                creator_id=creator_id,
                limit=limit,
                extract_details=extract_details
            )
            
            logger.info(f"[ConnectorService] Extracted {len(results)} items by creator ID")
            return results
            
        except Exception as e:
            logger.error(f"[ConnectorService] Extract by creator ID error: {e}")
            raise
    
    async def search_and_extract(
        self,
        platform: str | PlatformType,
        keyword: str,
        limit: int = 20,
        extract_details: bool = False
    ) -> List[Dict[str, Any]]:
        """搜索并提取内容

        Args:
            platform: 平台名称
            keyword: 搜索关键词
            limit: 限制数量
            extract_details: 是否提取详情

        Returns:
            搜索结果列表
        """
        try:
            connector = self._get_connector(platform)
            logger.info(f"[ConnectorService] Searching and extracting from {platform}, keyword={keyword}")
            
            results = await connector.search_and_extract(
                keyword=keyword,
                limit=limit,
                extract_details=extract_details
            )
            
            logger.info(f"[ConnectorService] Found {len(results)} search results")
            return results
            
        except Exception as e:
            logger.error(f"[ConnectorService] Search and extract error: {e}")
            raise

    async def login(
        self,
        platform: PlatformType,
        method: LoginMethod,
        **kwargs
    ) -> bool:
        """登录平台

        Args:
            platform: 平台名称
            method: 登录方法 (目前仅支持 cookie)
            **kwargs: 登录参数，例如 cookies, source, source_id

        Returns:
            是否登录成功
        """
        try:
            if platform == PlatformType.XIAOHONGSHU and method == LoginMethod.COOKIE:
                cookies = kwargs.get("cookies", {})
                if not cookies:
                    raise ValueError("Cookie 登录需要提供 cookies 参数")

                connector = self._get_connector(platform)
                
                # 获取 source 和 source_id
                source = kwargs.get("source", "default")
                source_id = kwargs.get("source_id", "default")
                
                logger.info(f"[ConnectorService] Logging in to {platform} with cookies for source:{source}, source_id:{source_id}")
                context_id = await connector.login_with_cookies(cookies, source, source_id)

                logger.info(f"[ConnectorService] Login Res: context_id: {context_id}")

                return context_id
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
