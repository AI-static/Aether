# -*- coding: utf-8 -*-
"""
Sanic应用配置
"""
from sanic import Sanic
from sanic.config import Config
from types import SimpleNamespace
import time
import traceback
from sanic.request import Request
from sanic.response import HTTPResponse, BaseHTTPResponse, json
from sanic.exceptions import NotFound
from sanic_cors import CORS
from sanic_ext import Extend
import uuid
from config.settings import settings
from utils.logger import logger


def create_app() -> Sanic:
    """创建Sanic应用实例"""
    app: Sanic[Config, SimpleNamespace] = Sanic("Aether")

    # 配置
    app.config.REQUEST_MAX_SIZE = 1024 * 1024 * 200
    app.ctx.settings = settings
    
    # 扩展
    Extend(app)
    
    # CORS
    CORS(
        app,
        resources={r"/*": {"origins": "*"}},
        supports_credentials=True,
    )
    
    # WebSocket
    app.enable_websocket()
    
    # 静态文件服务（图床功能）
    app.static(
        "/images",
        settings.image_dir,
        name="images"
    )

    # 中间件
    setup_middleware(app)
    
    # 异常处理
    setup_exception_handlers(app)
    
    # 注册路由
    register_routes(app)
    
    # 数据库初始化
    setup_database(app)
    
    return app


def setup_middleware(app: Sanic):
    """设置中间件"""
    
    @app.middleware("request")
    async def request_context_middleware(request: Request) -> None:
        """请求上下文中间件"""
        user_ip = request.headers.get("X-Real-IP", "0.0.0.0")
        
        # 生成请求ID
        request_id = str(uuid.uuid4())
        request.ctx.request_id = request_id
        request.ctx.start_time = time.time()
        request.ctx.user_ip = user_ip
        
        # 记录请求
        logger.info(f"[{request_id}] {request.method} {request.path} - IP: {user_ip}")

    @app.middleware("response")
    async def response_middleware(request: Request, response: BaseHTTPResponse) -> None:
        """响应中间件"""
        try:
            if not hasattr(request.ctx, 'start_time'):
                return

            cost = time.time() - request.ctx.start_time
            request_id = getattr(request.ctx, 'request_id', 'unknown')
            
            logger.info(
                f"[{request_id}] 完成 | 耗时: {cost:.3f}s | 状态: {response.status}"
            )
        except Exception as ex:
            logger.error(f"响应日志记录异常: {ex}")


def setup_exception_handlers(app: Sanic):
    """设置异常处理"""
    
    @app.exception(NotFound)
    async def not_found_handler(request: Request, exc: NotFound) -> HTTPResponse:
        """404处理"""
        from api.schema.response import BaseResponse, ErrorCode, ErrorMessage
        return json(
            BaseResponse(
                code=ErrorCode.NOT_FOUND,
                message=ErrorMessage.NOT_FOUND
            ).dict(),
            status=404
        )
    
    @app.exception(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        """全局异常处理"""
        from api.schema.response import BaseResponse, ErrorCode, ErrorMessage
        from utils.exceptions import BusinessException
        
        # 业务异常处理
        if isinstance(exc, BusinessException):
            logger.warning(f"业务异常: {exc.message} - {exc.details}")
            # 根据错误码确定HTTP状态码
            status = 400
            if exc.code >= 500:
                status = 500
            elif exc.code == 404:
                status = 404
            elif exc.code == 600:  # 图片相关业务错误
                status = 400
                
            return json(
                BaseResponse(
                    code=exc.code,
                    message=exc.message,
                    data=exc.details if exc.details else None
                ).dict(),
                status=status
            )
        
        # 系统异常处理
        logger.error(f"系统异常: {exc}\n{traceback.format_exc()}")
        return json(
            BaseResponse(
                code=ErrorCode.INTERNAL_ERROR,
                message=ErrorMessage.INTERNAL_ERROR
            ).dict(),
            status=500
        )


def register_routes(app: Sanic):
    """注册路由"""
    
    # 健康检查
    @app.route("/health")
    async def health_check(request: Request):
        """健康检查"""
        return {"status": "ok", "service": "aether"}
    
    # 注册业务路由
    from api.routes.config import bp as config_bp
    from api.routes.image import bp as image_bp
    app.blueprint(config_bp)
    app.blueprint(image_bp)


def setup_database(app: Sanic):
    """设置数据库连接"""
    # TODO: 初始化ORM连接
    pass