# Aether - 业务适配层服务

## 项目简介

Aether 是一个轻量级的业务适配层（Business Adaptation Layer），作为上层业务系统与底层服务之间的桥梁。它不提供具体的服务能力，而是负责：

- **协议转换**：将底层服务的API格式转换为业务系统需要的格式
- **业务适配**：封装底层接口，添加业务逻辑，满足特定场景需求
- **服务聚合**：组合多个底层服务，提供统一的业务接口
- **能力增强**：在基础服务之上添加缓存、限流、监控等增强功能

### 典型应用场景

#### 飞书插件场景
- **底层**：Ezlink提供图片生成API
- **适配层**：Aether接收飞书的请求，进行参数转换、权限验证、结果缓存等
- **上层**：飞书插件调用简单的接口完成图片生成

#### 企业能力对接
- 将第三方SaaS服务适配为企业内部标准接口
- 屏蔽不同供应商的API差异
- 提供统一的调用方式和错误处理

## 项目结构

```
aether/
├── config/              # 配置管理
│   ├── settings.py      # 应用配置
│   └── gunicorn.py      # Gunicorn部署配置
├── api/                 # API接口层
│   ├── routes/          # 路由定义
│   │   └── config.py     # 配置相关API
│   └── models/          # API数据模型
│       └── base.py       # 基础响应模型
├── services/            # 业务服务层（核心）
│   └── config_service.py # 配置业务逻辑
├── adapters/            # 第三方服务适配器
│   └── ezlink_adapter.py # Ezlink服务适配器
├── models/              # ORM数据模型
│   └── config.py        # 配置数据模型
├── utils/               # 工具函数
│   ├── logger.py        # 日志工具
│   ├── cache.py         # 缓存工具（Redis客户端）
│   └── helpers.py       # 辅助函数
├── app.py               # Sanic应用配置
├── main.py              # 应用入口
└── tests/               # 测试目录
```

## 技术栈

- **Web框架**: Sanic (异步Web框架)
- **配置管理**: Pydantic Settings
- **缓存**: Redis (同步客户端)
- **日志**: Loguru
- **HTTP客户端**: httpx (支持HTTP/2)
- **ORM**: Tortoise-ORM (PostgreSQL/MySQL)
- **部署**: Docker + Gunicorn

## 快速开始

### 环境要求
- Python 3.11+
- Redis
- PostgreSQL/MySQL (可选)

### 安装依赖

```bash
# 使用Poetry安装
poetry install

# 或使用pip
pip install -e .
```

### 配置环境变量

复制环境变量模板：
```bash
cp .env.example .env
```

编辑 `.env` 文件：
```env
# 应用配置
APP_NAME=Aether
APP_PORT=8000
APP_DEBUG=false

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# 数据库配置（使用ORM时需要）
DB_URL=postgresql://user:password@localhost:5432/dbname

# Ezlink服务配置
EZLINK_API_KEY=your_api_key_here
EZLINK_BASE_URL=https://api.ezlink.com
```

### 运行服务

开发模式：
```bash
python main.py
```

或使用Sanic命令：
```bash
sanic app:create_app --dev
```

### 验证服务

健康检查：
```bash
curl http://localhost:8000/health
```

## API文档

### 配置管理API

#### 创建配置
```http
POST /api/v1/config
Content-Type: application/json

{
    "type_code": "ezlink_config",
    "key": "image_style",
    "name": "图片风格配置",
    "value": {
        "default_style": "realistic",
        "size": "1024x1024"
    },
    "description": "Ezlink图片生成默认配置",
    "tags": ["ezlink", "image"]
}
```

#### 获取配置
```http
GET /api/v1/config?key=image_style
```

#### 查询配置列表
```http
GET /api/v1/config/list?type_code=ezlink_config&page=1&page_size=20
```

#### 更新配置
```http
PUT /api/v1/config/{id}
Content-Type: application/json

{
    "value": {
        "default_style": "anime",
        "size": "1024x1024"
    }
}
```

#### 删除配置
```http
DELETE /api/v1/config/{id}
```

## 开发指南

### 添加新的适配器

1. 在 `adapters/` 目录下创建适配器文件：
```python
# adapters/your_service_adapter.py
import httpx
from utils.logger import logger
from utils.cache import redis_client

class YourServiceAdapter:
    async def call_api(self, params: dict):
        # 缓存检查
        cache_key = f"your_service:{hash(str(params))}"
        cached = redis_client.get(cache_key)
        if cached:
            return cached
            
        # 调用API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.yourservice.com/endpoint",
                json=params
            )
            result = response.json()
            
        # 缓存结果
        redis_client.set(cache_key, result, expire=300)
        
        return result
```

2. 在 `services/` 中创建业务服务：
```python
# services/your_service.py
from adapters.your_service_adapter import YourServiceAdapter

class YourService:
    def __init__(self):
        self.adapter = YourServiceAdapter()
    
    async def process_request(self, data: dict):
        # 业务逻辑处理
        adapted_data = self._adapt_params(data)
        result = await self.adapter.call_api(adapted_data)
        return self._adapt_response(result)
```

3. 在 `api/routes/` 中创建路由：
```python
from sanic import Blueprint
from services.your_service import YourService

bp = Blueprint("your_service", url_prefix="/your-service")
service = YourService()

@bp.post("/process")
async def process_handler(request):
    result = await service.process_request(request.json)
    return {"code": 0, "data": result}
```

### 日志使用

```python
from utils.logger import logger

logger.info("普通信息")
logger.error("错误信息")
logger.debug("调试信息")
```

### 缓存使用

```python
from utils.cache import redis_client

# 设置缓存
redis_client.set("key", "value", expire=3600)

# 获取缓存
value = redis_client.get("key")

# 删除缓存
redis_client.delete("key")
```

## 部署指南

### Docker部署

构建镜像：
```bash
docker build -t aether .
```

运行容器：
```bash
docker run -p 8000:8000 --env-file .env aether
```

### Gunicorn部署

```bash
gunicorn -c config/gunicorn.py app:create_app()
```

### 生产环境配置

1. 设置合适的worker数量：
```python
# config/gunicorn.py
workers = 4  # CPU核心数 * 2
worker_class = "sanic.worker.GunicornWorker"
```

2. 配置反向代理（Nginx示例）：
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## 最佳实践

### 1. 适配器设计
- **单一职责**：每个适配器只对接一个外部服务
- **统一错误处理**：所有适配器应该有统一的错误处理和重试机制
- **合理缓存**：对不变或变化缓慢的数据进行缓存

### 2. 服务层设计
- **业务逻辑封装**：核心业务逻辑都在服务层实现
- **事务管理**：使用服务层管理数据库事务
- **参数验证**：在API层进行基础验证，服务层进行业务验证

### 3. 性能优化
- **连接池**：使用连接池管理数据库和Redis连接
- **批量操作**：尽可能使用批量操作减少请求次数
- **异步处理**：使用异步模式提高并发能力

## 贡献指南

1. Fork 项目
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 创建 Pull Request

## 许可证

MIT License