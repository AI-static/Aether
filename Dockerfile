# 推荐方案：Poetry 导出 + pip 安装

# 第一阶段：使用 Poetry 导出完整的 requirements.txt
FROM python:3.12-slim AS req-generator

# 设置 Debian 镜像源
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list

# 设置 PYPI 镜像
ARG PYPI_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PYPI_TRUSTED=pypi.tuna.tsinghua.edu.cn

# Poetry 环境变量
ENV POETRY_NO_INTERACTION=1 \
    POETRY_VENV_IN_PROJECT=1 \
    POETRY_CACHE_DIR=/tmp/poetry_cache

# 安装 Poetry
RUN pip config set global.index-url ${PYPI_URL} && \
    pip config set install.trusted-host ${PYPI_TRUSTED} && \
    python -m pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir poetry==2.0.0 poetry-plugin-export==1.9.0

# 配置 Poetry
RUN poetry config virtualenvs.create false

WORKDIR /app
COPY pyproject.toml poetry.lock* ./

# 导出 requirements.txt
RUN poetry export \
    --format requirements.txt \
    --output requirements.txt

# 验证导出结果
RUN echo "=== 导出验证 ===" && \
    echo "总依赖数量: $(wc -l < requirements.txt)" && \
    echo "关键依赖检查:" && \
    grep -E "(sanic|pydantic|httpx)" requirements.txt | head -5 || echo "某些关键依赖可能缺失"

# 第二阶段：使用 pip 安装依赖（更轻量的运行时镜像）
FROM python:3.12-slim AS runtime

# 设置 Debian 镜像源
RUN sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list.d/debian.sources || \
    sed -i 's/deb.debian.org/mirrors.ustc.edu.cn/g' /etc/apt/sources.list

# 环境变量设置
ENV API_VERSION=v1.0 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PROTOCOL_BUFFERS_PYTHON_IMPLEMENTATION="python" \
    TZ=Asia/Shanghai

# 设置 PYPI 镜像
ARG PYPI_URL=https://pypi.tuna.tsinghua.edu.cn/simple
ARG PYPI_TRUSTED=pypi.tuna.tsinghua.edu.cn

# 设置时区
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装编译依赖（某些 Python 包需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 复制生成的 requirements.txt
COPY --from=req-generator /app/requirements.txt ./

# 配置 pip 并安装所有依赖
RUN pip config set global.index-url ${PYPI_URL} && \
    pip config set install.trusted-host ${PYPI_TRUSTED} && \
    python -m pip install --no-cache-dir -U pip && \
    pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建非 root 用户
RUN adduser -u 5678 --disabled-password --gecos "" appuser && \
    chown -R appuser /app

USER appuser

# 启动命令
CMD ["gunicorn", "-c", "config/gunicorn.py", "main:app"]

# 构建镜像
# docker build -t aether:latest .

# 运行容器
# docker run -d -p 8000:8000 --name aether aether:latest

# [debug] 运行容器（挂载代码目录 + 开启debug模式）
# docker run -d -p 8001:8000 -v .:/app -e APP_DEBUG=true -e APP_AUTO_RELOAD=true --name aether-debug aether:latest