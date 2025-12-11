# -*- coding: utf-8 -*-

# 多进程
import multiprocessing
import os  # 引入 os 模块，用于读取环境变量
from config.settings import settings

"""gunicorn+gevent 的配置文件"""

# 读取 .env 文件中的环境变量
os.environ['TZ'] = 'Asia/Shanghai'

# 获取端口号，默认为 5000


# 绑定 ip + 端口
bind = f"0.0.0.0:{settings.app_port}"

# 进程数 = cpu数量（对于 I/O 密集型应用，可以将 workers 数量设置为 2 * CPU 核心数，以更好地利用 CPU 资源）
workers = 4
timeout = 600  # 增加到10分钟，以支持图片生成等长时间任务

# 线程数 = cpu数量
threads = 1

# 等待队列最大长度,超过这个长度的链接将被拒绝连接
backlog = 8192

# 工作模式--ASGI 工作器
worker_class = "uvicorn.workers.UvicornWorker"

# 最大客户客户端并发数量,对使用线程和协程的worker的工作有影响
# 服务器配置设置的值  1200：中小型项目  上万并发： 中大型
# 服务器硬件：宽带+数据库+内存
# 服务器的架构：集群 主从
worker_connections = 1200