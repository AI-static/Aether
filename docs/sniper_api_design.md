# Sniper API 设计文档

## 设计理念

这是一个专为 **Agent 交互** 设计的后台任务系统，与传统任务队列有本质区别：

### 核心差异

| 传统任务系统 | Agent 交互式任务 |
|------------|----------------|
| 配置参数化（给人看） | 自然语言目标（给 AI 理解） |
| 黑盒执行 | 透明过程（步骤链） |
| 静态结果 | 流式日志 + 最终结果 |
| 简单状态 | 丰富状态 + 进度追踪 |

### Agent 友好特性

1. **可解释性**：每个任务都有明确的目标描述
2. **过程透明**：记录每一步的输入输出
3. **实时反馈**：SSE 流式日志，AI 可实时调整
4. **上下文保留**：完整记录任务历史，支持断点续传

---

## 数据模型

### Task 模型 (`models/sniper.py`)

```python
class Task(Model):
    # 1. 任务目标（AI 理解上下文）
    goal = "分析'agent面试'的爆款趋势"
    context = {"keywords": ["agent面试"], "platform": "xiaohongshu"}

    # 2. 执行过程（决策链）
    steps = [
        {
            "step": 1,
            "name": "关键词裂变",
            "description": "基于核心词裂变搜索词",
            "input": {"keyword": "agent面试"},
            "output": {"keywords": ["agent面试", "AI面试技巧"]},
            "status": "completed"
        }
    ]

    # 3. 任务结果（AI 产出）
    result = {
        "summary": "发现3个爆款方向",
        "insights": [...],
        "action_items": [...]
    }

    # 4. 流式日志（实时反馈）
    logs = [
        {"time": "10:00:00", "level": "info", "message": "🚀 开始执行"}
    ]

    # 5. 状态追踪
    status = "running"
    progress = 50
```

---

## API 接口

### 1. 创建趋势分析任务

**POST** `/sniper/trend`

```json
{
  "keywords": ["agent面试", "AI面试"],
  "platform": "xiaohongshu",
  "depth": "deep",
  "limit": 50
}
```

**响应**：
```json
{
  "code": 0,
  "message": "任务已创建，后台执行中",
  "data": {
    "task_id": "uuid",
    "status": "pending",
    "progress": 0,
    "goal": "分析关键词 ['agent面试', 'AI面试'] 在 xiaohongshu 上的爆款趋势，生成选题建议",
    "created_at": "2025-12-27T10:00:00"
  }
}
```

### 2. 创建创作者监控任务

**POST** `/sniper/monitor`

```json
{
  "creator_ids": ["user_id_1", "user_id_2"],
  "platform": "xiaohongshu",
  "days": 7
}
```

### 3. 查询任务详情

**GET** `/sniper/task/{task_id}`

**响应**：
```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "task_type": "trend_analysis",
    "status": "completed",
    "progress": 100,
    "goal": "...",
    "context": {...},
    "steps": [...],
    "result": {
      "summary": "共分析85篇去重笔记...",
      "insights": [...],
      "top_notes": [...],
      "action_items": [...]
    },
    "logs": [...]
  }
}
```

### 4. 获取任务状态（轮询）

**GET** `/sniper/task/{task_id}/status`

**响应**：
```json
{
  "code": 0,
  "data": {
    "task_id": "uuid",
    "status": "running",
    "progress": 60,
    "created_at": "2025-12-27T10:00:00",
    "started_at": "2025-12-27T10:00:05",
    "has_result": false,
    "has_error": false,
    "log_count": 15
  }
}
```

### 5. 流式获取日志（SSE）

**GET** `/sniper/task/{task_id}/logs`

**SSE 事件流**：
```
data: {"type": "logs", "logs": [{"time": "10:00:00", "message": "🚀 开始执行"}]}

event: complete
data: {"status": "completed", "result": {...}}
```

### 6. 查询任务列表

**POST** `/sniper/tasks`

```json
{
  "source_id": "user_123",
  "status": "completed",
  "task_type": "trend_analysis",
  "limit": 20
}
```

### 7. 取消任务

**DELETE** `/sniper/task/{task_id}`

---

## 后台任务执行流程

### 趋势分析任务 (`xhs_trend.py` 集成)

```
1. 创建任务 → status=pending, progress=0
   ↓
2. 开始执行 → status=running, progress=10
   ↓
3. 关键词裂变 → progress=20, logs=["裂变结果: [...]"]
   ↓
4. 搜索去重 → progress=50, logs=["去重后获得85篇"]
   ↓
5. 获取详情 → progress=70, logs=["详情获取完成"]
   ↓
6. Agent分析 → progress=95, logs=["分析完成"]
   ↓
7. 生成结果 → status=completed, progress=100
```

### 创作者监控任务 (`xhs_creator.py` 集成)

```
1. 创建任务
2. 初始化监控器
3. 执行监控（批量获取内容）
4. 筛选新内容
5. 生成报告
6. 完成任务
```

---

## 使用示例

### Python 客户端

```python
import asyncio
import aiohttp

async def create_trend_task():
    async with aiohttp.ClientSession() as session:
        # 1. 创建任务
        resp = await session.post(
            "http://localhost:8000/sniper/trend",
            json={
                "keywords": ["agent面试"],
                "platform": "xiaohongshu",
                "depth": "deep"
            },
            headers={"Authorization": "Bearer api_key"}
        )
        data = await resp.json()
        task_id = data["data"]["task_id"]

        # 2. 轮询状态
        while True:
            resp = await session.get(
                f"http://localhost:8000/sniper/task/{task_id}/status"
            )
            status = await resp.json()
            progress = status["data"]["progress"]
            print(f"进度: {progress}%")

            if progress == 100:
                break
            await asyncio.sleep(2)

        # 3. 获取结果
        resp = await session.get(
            f"http://localhost:8000/sniper/task/{task_id}"
        )
        result = await resp.json()
        print(result["data"]["result"])
```

### SSE 流式监听

```python
import sseclient

def stream_logs(task_id):
    client = sseclient.SSEClient(
        f"http://localhost:8000/sniper/task/{task_id}/logs"
    )

    for event in client.events():
        if event.event == "complete":
            print("任务完成:", event.data)
            break
        elif event.data:
            data = json.loads(event.data)
            for log in data.get("logs", []):
                print(f"[{log['time']}] {log['message']}")
```

---

## 数据库设计

### 表结构

```sql
CREATE TABLE sniper_tasks (
    id UUID PRIMARY KEY,
    source_id VARCHAR(100),
    task_type VARCHAR(50),
    config JSONB,
    status VARCHAR(20),
    progress INTEGER,
    result JSONB,
    error_message TEXT,
    logs JSONB,
    created_at TIMESTAMP,
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    metadata JSONB
);

CREATE INDEX idx_sniper_tasks_source_status ON sniper_tasks(source_id, status);
CREATE INDEX idx_sniper_tasks_type_status ON sniper_tasks(task_type, status);
CREATE INDEX idx_sniper_tasks_created ON sniper_tasks(created_at);
```

---

## 优势总结

1. **Agent 可读**：自然语言目标 + 步骤链，AI 理解上下文
2. **实时反馈**：SSE 流式日志，用户/AI 可实时监控
3. **结果丰富**：不仅有数据，还有分析和建议
4. **去重处理**：自动处理多关键词重复问题
5. **后台执行**：不阻塞，支持并发任务
6. **状态完整**：从创建到完成的全生命周期追踪

---

## 扩展性

### 支持新任务类型

只需：
1. 在 `TaskType` 添加枚举
2. 在 `TaskService` 添加执行方法
3. 在 `api/routes/sniper.py` 添加创建端点

### 支持新平台

在 `config` 中指定 `platform`，服务层自动路由到对应连接器。

---

## 注意事项

1. **数据库迁移**：需要先执行 Tortoise ORM 迁移
2. **Playwright 初始化**：确保 app.ctx.playwright 可用
3. **任务清理**：长时间运行的任务建议设置超时
4. **日志限制**：避免 logs 字段过大，可定期清理
