# -*- coding: utf-8 -*-
"""连接器API路由"""
from sanic import Blueprint, Request
from sanic.response import json, ResponseStream
import ujson as json_lib
import asyncio
from services.connectors import connector_service
from utils.logger import logger
from api.schema.response import BaseResponse, ErrorCode, ErrorMessage
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Dict, Any

# 创建蓝图
connectors_bp = Blueprint("connectors", url_prefix="/connectors")


# ==================== 请求模型 ====================

class ExtractRequest(BaseModel):
    """提取请求"""
    urls: List[str] = Field(..., description="要提取的URL列表")
    platform: Optional[str] = Field(None, description="平台名称（xiaohongshu/wechat/generic），不指定则自动检测")
    concurrency: int = Field(1, description="并发数量，默认1（串行）", ge=1, le=10)


class MonitorRequest(BaseModel):
    """监控请求"""
    urls: List[str] = Field(..., description="要监控的URL列表")
    platform: Optional[str] = Field(None, description="平台名称，不指定则自动检测")
    check_interval: int = Field(3600, description="检查间隔（秒），默认1小时")
    webhook_url: Optional[str] = Field(None, description="可选的 webhook 回调地址")


class HarvestRequest(BaseModel):
    """采收请求"""
    platform: str = Field(..., description="平台名称（xiaohongshu/wechat）")
    user_id: str = Field(..., description="用户ID或账号标识")
    limit: Optional[int] = Field(None, description="限制数量")


class PublishRequest(BaseModel):
    """发布请求"""
    platform: str = Field(..., description="平台名称（xiaohongshu）")
    content: str = Field(..., description="内容文本")
    content_type: str = Field("text", description="内容类型（text/image/video）")
    images: Optional[List[str]] = Field(None, description="图片URL列表")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    session_id: Optional[str] = Field(None, description="可选的会话ID，用于复用已登录会话")


class LoginRequest(BaseModel):
    """登录请求"""
    platform: str = Field(..., description="平台名称（xiaohongshu）")
    method: str = Field("cookie", description="登录方法（目前仅支持 cookie）")
    session_id: Optional[str] = Field(None, description="可选的会话ID")
    cookies: Optional[Dict[str, str]] = Field(None, description="Cookie 数据")


# ==================== 路由处理 ====================

@connectors_bp.post("/extract")
async def extract_content(request: Request):
    """提取URL内容 - SSE 流式输出

    每提取完一个URL就立即返回结果，不需要等待所有URL都提取完成
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
            await response.write(f"data: {json_lib.dumps(ack_msg)}\n\n")

            success_count = 0
            total_count = 0

            # 逐个 yield 提取结果
            async for result in connector_service.extract_urls_stream(
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
                    await response.write(f"data: {json_lib.dumps(result_msg)}\n\n")
                    logger.info(f"[SSE Extract] {client_id} Sent result {total_count}/{len(data.urls)}")
                except Exception as send_error:
                    logger.error(f"[SSE Extract] {client_id} 发送失败: {send_error}")
                    break

            # 发送完成消息
            complete_msg = {
                "type": "complete",
                "message": f"提取完成：{success_count}/{total_count} 成功",
                "summary": {
                    "total": total_count,
                    "success_count": success_count,
                    "failed_count": total_count - success_count
                }
            }
            await response.write(f"data: {json_lib.dumps(complete_msg)}\n\n")

        except ValidationError as e:
            logger.error(f"[SSE Extract] {client_id} 参数验证失败: {e}")
            error_msg = {"type": "error", "message": "参数验证失败", "detail": str(e)}
            try:
                await response.write(f"data: {json_lib.dumps(error_msg)}\n\n")
            except:
                pass
        except Exception as e:
            logger.error(f"[SSE Extract] {client_id} 提取异常: {e}", exc_info=True)
            error_msg = {"type": "error", "message": str(e)}
            try:
                await response.write(f"data: {json_lib.dumps(error_msg)}\n\n")
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

        success = await connector_service.login(
            platform=data.platform,
            method=data.method,
            session_id=data.session_id,
            cookies=data.cookies or {}
        )

        return json(BaseResponse(
            code=ErrorCode.SUCCESS if success else ErrorCode.INTERNAL_ERROR,
            message="登录成功" if success else "登录失败",
            data={"success": success}
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
            "name": "xiaohongshu",
            "display_name": "小红书",
            "features": ["extract", "monitor", "harvest", "publish", "login"],
            "description": "小红书平台连接器，支持内容提取、发布、监控和采收"
        },
        {
            "name": "wechat",
            "display_name": "微信公众号",
            "features": ["extract", "monitor", "harvest"],
            "description": "微信公众号连接器，支持文章提取、监控和采收"
        },
        {
            "name": "generic",
            "display_name": "通用网站",
            "features": ["extract", "monitor"],
            "description": "通用网站连接器，支持任意网站的内容提取和监控"
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


@connectors_bp.get("/monitor")
async def monitor_sse(request: Request):
    """
    SSE 监控端点 - 实时推送URL变化

    使用方法：
    GET /connectors/monitor?urls=url1,url2&platform=xiaohongshu&interval=60

    参数：
    - urls: URL列表，用逗号分隔
    - platform: 平台名称（可选，不指定则自动检测）
    - interval: 检查间隔（秒），默认3600
    """

    async def event_stream(response):
        client_id = f"client_{id(response)}"
        logger.info(f"[SSE] 客户端连接: {client_id}")

        try:
            # 1. 从查询参数获取配置
            urls_param = request.args.get("urls", "")
            platform = request.args.get("platform", None)

            try:
                check_interval = int(request.args.get("interval", "3600"))
            except ValueError:
                check_interval = 3600

            # 解析 URL 列表
            urls = [url.strip() for url in urls_param.split(",") if url.strip()]

            if not urls:
                error_data = {"type": "error", "message": "请提供至少一个URL (参数: urls)"}
                await response.write(f"data: {json_lib.dumps(error_data)}\n\n")
                return

            logger.info(f"[SSE] {client_id} 开始监控 {len(urls)} 个URL, platform={platform}, interval={check_interval}s")

            # 2. 发送确认消息
            ack_msg = {
                "type": "ack",
                "message": "监控已启动",
                "config": {
                    "urls": urls,
                    "platform": platform,
                    "check_interval": check_interval,
                    "url_count": len(urls)
                }
            }
            await response.write(f"data: {json_lib.dumps(ack_msg)}\n\n")

            # 3. 开始监控并实时推送变化
            async for change in connector_service.monitor_urls(
                urls=urls,
                platform=platform,
                check_interval=check_interval,
                webhook_url=None
            ):
                push_msg = {
                    "type": "change",
                    "data": change,
                    "timestamp": change.get("timestamp")
                }

                try:
                    await response.write(f"data: {json_lib.dumps(push_msg)}\n\n")
                    logger.debug(f"[SSE] {client_id} 推送变化: {change.get('url')}")
                    await asyncio.sleep(0.1)
                except Exception as send_error:
                    logger.error(f"[SSE] {client_id} 发送失败: {send_error}")
                    break

        except Exception as e:
            logger.error(f"[SSE] {client_id} 监控异常: {e}", exc_info=True)
            error_msg = {"type": "error", "message": str(e)}
            try:
                await response.write(f"data: {json_lib.dumps(error_msg)}\n\n")
            except:
                pass

        finally:
            logger.info(f"[SSE] 客户端断开: {client_id}")

    return ResponseStream(
        event_stream,
        headers={
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )



