# -*- coding: utf-8 -*-
"""连接器API路由"""
from sanic import Blueprint, Request
from sanic.response import json, ResponseStream
import ujson as json_lib
import asyncio
from services.connectors import connector_service
from utils.logger import logger
from api.schema.base import BaseResponse, ErrorCode, ErrorMessage
from api.schema.connectors import ExtractRequest, HarvestRequest, PublishRequest, LoginRequest
from pydantic import BaseModel, Field, ValidationError
from models.connectors import PlatformType

# 创建蓝图
connectors_bp = Blueprint("connectors", url_prefix="/connectors")


# ==================== 路由处理 ====================

@connectors_bp.post("/extract-summary")
async def extract_summary(request: Request):
    """提取URL内容摘要 - SSE 流式输出

    使用Agent提取，每提取完一个URL就立即返回结果，不需要等待所有URL都提取完成
    """

    async def event_stream(response):
        client_id = f"client_{id(response)}"
        logger.info(f"[SSE Extract] 客户端连接: {client_id}")

        try:
            data = ExtractRequest(**request.json)
            logger.info(f"[SSE Extract] 收到内容提取请求: {len(data.urls)} 个URL, platform={data.platform}")

            # 发送确认消息
            ack_msg = {
                "type": "start",
                "message": "提取已启动",
                "config": {
                    "urls": data.urls,
                    "platform": data.platform,
                    "url_count": len(data.urls),
                    "concurrency": data.concurrency
                }
            }
            await response.write(f"data: {json_lib.dumps(ack_msg, ensure_ascii=False)}\n\n")

            success_count = 0
            total_count = 0

            # 逐个 yield 提取结果
            async for result in connector_service.extract_summary(
                urls=data.urls,
                platform=data.platform,
                concurrency=data.concurrency
            ):
                total_count += 1
                if result.get("success"):
                    success_count += 1

                logger.info(f"[SSE Extract] {client_id} Received result {total_count}/{len(data.urls)} for {result.get('url')}")

                # 推送单个URL的提取结果
                result_msg = {
                    "type": "result",
                    "data": result,
                    "progress": {
                        "current": total_count,
                        "total": len(data.urls),
                        "success_count": success_count
                    }
                }

                try:
                    await response.write(f"data: {json_lib.dumps(result_msg, ensure_ascii=False)}\n\n")
                    logger.info(f"[SSE Extract] {client_id} Sent result {total_count}/{len(data.urls)}")
                except Exception as send_error:
                    logger.error(f"[SSE Extract] {client_id} 发送失败: {send_error}")
                    break

            # 发送完成消息
            complete_msg = {
                "type": "complete",
                "message": f'提取完成：{success_count}/{total_count} 成功',
                "summary": {
                    "total": total_count,
                    "success_count": success_count,
                    "failed_count": total_count - success_count
                }
            }
            await response.write(f"data: {json_lib.dumps(complete_msg, ensure_ascii=False)}\n\n")

        except ValidationError as e:
            logger.error(f"[SSE Extract] {client_id} 参数验证失败: {e}")
            error_msg = {"type": "error", "message": "参数验证失败", "detail": str(e)}
            try:
                await response.write(f"data: {json_lib.dumps(error_msg, ensure_ascii=False)}\n\n")
            except:
                pass
        except Exception as e:
            logger.error(f"[SSE Extract] {client_id} 提取异常: {e}", exc_info=True)
            error_msg = {"type": "error", "message": str(e)}
            try:
                await response.write(f"data: {json_lib.dumps(error_msg, ensure_ascii=False)}\n\n")
            except:
                pass
        finally:
            logger.info(f"[SSE Extract] 客户端断开: {client_id}")

    return ResponseStream(
        event_stream,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@connectors_bp.post("/harvest")
async def harvest_content(request: Request):
    """采收用户内容"""
    try:
        data = HarvestRequest(**request.json)
        logger.info(f"收到采收请求: platform={data.platform}, user_id={data.user_id}, limit={data.limit}")

        results = await connector_service.harvest_user_content(
            platform=data.platform,
            user_id=data.user_id,
            limit=data.limit
        )

        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=f"采收完成：获取到 {len(results)} 条内容",
            data={
                "results": results,
                "total": len(results)
            }
        ).model_dump())

    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message=str(e),
            data={"error": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"采收内容失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@connectors_bp.post("/publish")
async def publish_content(request: Request):
    """发布内容到平台"""
    try:
        data = PublishRequest(**request.json)
        logger.info(f"收到发布请求: platform={data.platform}, type={data.content_type}")

        result = await connector_service.publish_content(
            platform=data.platform,
            content=data.content,
            content_type=data.content_type,
            images=data.images or [],
            tags=data.tags or [],
            session_id=data.session_id
        )

        return json(BaseResponse(
            code=ErrorCode.SUCCESS if result.get("success") else ErrorCode.INTERNAL_ERROR,
            message="发布成功" if result.get("success") else "发布失败",
            data=result
        ).model_dump())

    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message=str(e),
            data={"error": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"发布内容失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@connectors_bp.post("/login")
async def login(request: Request):
    """登录平台"""
    try:
        data = LoginRequest(**request.json)
        logger.info(f"收到登录请求: platform={data.platform}, method={data.method}")

        # 从认证中间件获取 source 和 source_id
        auth_info = getattr(request.ctx, 'auth_info', {}) if hasattr(request, 'ctx') else {}
        if not auth_info:
            return json(BaseResponse(
                code=ErrorCode.UNAUTHORIZED,
                message=ErrorMessage.UNAUTHORIZED,
                data={"detail": "登陆状态有问题"}
            ).model_dump(), status=400)

        logger.info(f"[Auth] 从认证上下文获取: 鉴权数据AuthInfo: {auth_info.source}")

        # 调用 connector_service 的 login 方法
        context_id = await connector_service.login(
            platform=data.platform,
            method=data.method,
            cookies=data.cookies or {},
            source=auth_info.source.value,
            source_id=auth_info.source_id
        )

        return json(BaseResponse(
            code=ErrorCode.SUCCESS if context_id else ErrorCode.INTERNAL_ERROR,
            message="登录成功" if context_id else "登录失败",
            data={
                "context_id": context_id,
                "source": auth_info.source,
                "source_id": auth_info.source_id
            }
        ).model_dump())

    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message=str(e),
            data={"error": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"登录失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@connectors_bp.get("/platforms")
async def list_platforms(request: Request):
    """获取支持的平台列表"""
    platforms = [
        {
            "name": PlatformType.XIAOHONGSHU.value,
            "display_name": "小红书",
            "features": ["extract", "harvest", "publish", "login"],
            "description": "小红书平台连接器，支持内容提取、发布、采收"
        },
        {
            "name": PlatformType.WECHAT.value,
            "display_name": "微信公众号",
            "features": ["extract_summary", "get_note_detail", "harvest"],
            "description": "微信公众号连接器，支持文章摘要提取、详情获取、采收"
        },
        {
            "name": PlatformType.GENERIC.value,
            "display_name": "通用网站",
            "features": ["extract"],
            "description": "通用网站连接器，支持任意网站的内容提取"
        }
    ]

    return json(BaseResponse(
        code=ErrorCode.SUCCESS,
        message="获取平台列表成功",
        data={
            "platforms": platforms,
            "total": len(platforms)
        }
    ).model_dump())


@connectors_bp.post("/get-note-detail")
async def get_note_detail(request: Request):
    """获取笔记/文章详情（快速提取，不使用Agent）
    
    适合场景：
    - 批量获取文章内容和图片
    - 快速抓取文章基本信息
    - 不需要深度AI分析的场景
    
    性能特点：
    - 速度快，通常2-5秒完成单篇文章
    - 资源消耗少
    - 直接提取，不依赖AI
    """
    try:
        data = ExtractRequest(**request.json)
        logger.info(f"收到快速提取请求: {len(data.urls)} 个URL, platform={data.platform}")
        
        # 获取笔记详情
        results = await connector_service.get_note_details(
            urls=data.urls,
            platform=data.platform
        )
        
        # 统计结果
        success_count = sum(1 for r in results if r.get("success"))
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=f"快速提取完成：{success_count}/{len(results)} 成功",
            data={
                "results": results,
                "summary": {
                    "total": len(results),
                    "success_count": success_count,
                    "failed_count": len(results) - success_count,
                    "method": "fast_extraction"
                }
            }
        ).model_dump())
        
    except ValidationError as e:
        logger.error(f"参数验证失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.VALIDATION_ERROR,
            message=ErrorMessage.VALIDATION_ERROR,
            data={"detail": str(e)}
        ).model_dump(), status=400)
    except ValueError as e:
        logger.error(f"参数错误: {e}")
        return json(BaseResponse(
            code=ErrorCode.BAD_REQUEST,
            message=str(e),
            data={"error": str(e)}
        ).model_dump(), status=400)
    except Exception as e:
        logger.error(f"获取笔记详情失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@connectors_bp.post("/extract-by-creator")
async def extract_by_creator(request: Request):
    """通过创作者ID提取内容"""
    try:
        data = request.json
        creator_id = data.get("creator_id")
        platform = data.get("platform")
        limit = data.get("limit")
        extract_details = data.get("extract_details", False)
        
        if not creator_id or not platform:
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message="缺少 creator_id 或 platform 参数",
                data={"error": "creator_id and platform are required"}
            ).model_dump(), status=400)
        
        logger.info(f"通过创作者ID提取内容: platform={platform}, creator_id={creator_id}")
        
        results = await connector_service.extract_by_creator_id(
            platform=platform,
            creator_id=creator_id,
            limit=limit,
            extract_details=extract_details
        )
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=f"提取完成：获取到 {len(results)} 条内容",
            data={
                "results": results,
                "total": len(results)
            }
        ).model_dump())
        
    except Exception as e:
        logger.error(f"提取失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)


@connectors_bp.post("/search-and-extract")
async def search_and_extract(request: Request):
    """搜索并提取内容"""
    try:
        data = request.json
        keyword = data.get("keyword")
        platform = data.get("platform")
        limit = data.get("limit", 20)
        extract_details = data.get("extract_details", False)
        
        if not keyword or not platform:
            return json(BaseResponse(
                code=ErrorCode.BAD_REQUEST,
                message="缺少 keyword 或 platform 参数",
                data={"error": "keyword and platform are required"}
            ).model_dump(), status=400)
        
        logger.info(f"搜索并提取内容: platform={platform}, keyword={keyword}")
        
        results = await connector_service.search_and_extract(
            platform=platform,
            keyword=keyword,
            limit=limit,
            extract_details=extract_details
        )
        
        return json(BaseResponse(
            code=ErrorCode.SUCCESS,
            message=f"搜索完成：找到 {len(results)} 条结果",
            data={
                "results": results,
                "total": len(results),
                "keyword": keyword
            }
        ).model_dump())
        
    except Exception as e:
        logger.error(f"搜索失败: {e}")
        return json(BaseResponse(
            code=ErrorCode.INTERNAL_ERROR,
            message=ErrorMessage.INTERNAL_ERROR,
            data={"error": str(e)}
        ).model_dump(), status=500)




