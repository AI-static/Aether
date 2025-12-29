# Sniper Task 设计 - Agent 可读的上下文记录

## 核心理念

**Task 表 = 记忆 + 上下文**

不是传统的任务队列，而是：
- 记录执行过程（给 AI 看）
- 存储共享上下文（供后续步骤使用）
- 支持 Agent 查看并决定下一步

---

## 数据结构

```python
class Task(Model):
    id: UUID
    source_id: str          # 谁发起的
    task_type: str          # 任务类型
    config: dict            # 原始配置

    status: str             # 状态
    progress: int           # 进度

    # 🌟 核心：共享上下文
    shared_context: dict    # 所有步骤的结果都在这里
    {
        "step_1_keywords": ["agent面试", "AI面试技巧"],
        "step_2_notes": [...],
        "step_3_details": [...],
        "step_4_analysis": {...}
    }

    # 🌟 核心：执行日志
    logs: list              # 每一步的输入输出
    [
        {
            "step": 1,
            "name": "关键词裂变",
            "input": {"core_keyword": "agent面试"},
            "output": {"keywords": [...]},
            "status": "completed"
        }
    ]

    result: dict            # 最终结果
    error: dict             # 错误信息
```

---

## 执行流程

### 1. 创建任务
```python
POST /sniper/trend
{
  "keywords": ["agent面试"],
  "platform": "xiaohongshu"
}

# 返回
{
  "task_id": "uuid",
  "status": "pending",
  "goal": "分析关键词爆款趋势"
}
```

### 2. 后台执行（记录上下文）
```python
# Service 执行逻辑
async def _run_trend_analysis(task):
    # Step 1: 关键词裂变
    keywords = await generate_keywords()
    await task.update_context("step_1_keywords", keywords)
    await task.log_step(1, "关键词裂变", input, output)
    task.progress = 20

    # Step 2: 搜索去重
    notes = await search_and_deduplicate(keywords)
    await task.update_context("step_2_notes", notes)
    await task.log_step(2, "搜索去重", input, output)
    task.progress = 50

    # Step 3: 获取详情
    details = await fetch_details(notes)
    await task.update_context("step_3_details", details)
    await task.log_step(3, "获取详情", input, output)
    task.progress = 70

    # Step 4: Agent 分析
    analysis = await agent.analyze(details)
    await task.update_context("step_4_analysis", analysis)
    await task.log_step(4, "Agent分析", input, output)
    task.progress = 95

    # 完成
    await task.complete({"final_result": ...})
```

### 3. 查询任务（Agent 可读）
```python
GET /sniper/task/{task_id}

# 返回 - Agent 可以直接理解
{
  "task_id": "uuid",
  "task_type": "trend_analysis",
  "status": "completed",
  "progress": 100,
  "config": {"keywords": ["agent面试"]},

  # 🌟 Agent 看这里就知道发生了什么
  "shared_context": {
    "step_1_keywords": ["agent面试", "AI面试技巧"],
    "step_2_notes": [...],
    "step_3_details": [...],
    "step_4_analysis": {...}
  },

  # 🌟 完整的执行历史
  "logs": [
    {"step": 1, "name": "关键词裂变", "output": {...}},
    {"step": 2, "name": "搜索去重", "output": {...}},
    ...
  ],

  "result": {...},
  "error": null,

  # 🌟 提示下一步
  "next_step_hint": "任务已完成，可查看结果"
}
```

---

## Agent 如何使用 Task 数据

### 场景 1: 查看执行历史
```python
# Agent 读取 Task 数据
task_data = await get_task(task_id)

# Agent 理解：
# "哦，Step 1 裂变出了3个关键词"
# "Step 2 搜索并去重，得到85篇笔记"
# "Step 3 获取了详情"
# "Step 4 我已经分析过了"
```

### 场景 2: 决定下一步
```python
# 如果任务失败
if task_data["status"] == "failed":
    error = task_data["error"]
    context = task_data["shared_context"]

    # Agent 可以分析：
    # "Step 2 失败了，但 Step 1 的关键词是好的"
    # "建议：用 Step 1 的关键词重试，或者换平台"

    # Agent 可以生成新的指令给代码
    new_config = {
        "keywords": context["step_1_keywords"],
        "platform": "wechat"  # 换平台
    }
```

### 场景 3: 继续执行
```python
# 如果任务只完成了一半
if task_data["status"] == "running":
    current_step = task_data["logs"][-1]["step"]

    # Agent 可以决定：
    # "Step 3 已完成，继续 Step 4"
    # 或者 "Step 3 数据不够，补充 Step 2.5"
```

---

## 优势

### 1. **记忆持久化**
- 所有步骤结果都存入 `shared_context`
- 即使服务重启，Task 数据还在
- Agent 随时可以查看历史

### 2. **上下文传递**
```python
# Step 1 输出
shared_context["step_1_keywords"] = ["agent面试", "AI面试技巧"]

# Step 2 输入（直接读取）
keywords = shared_context["step_1_keywords"]

# Step 2 输出
shared_context["step_2_notes"] = [...]

# Step 3 输入
notes = shared_context["step_2_notes"]
```

### 3. **Agent 可读性**
```python
# 传统方式（给机器看）
{
  "config": {"keywords": [...]},
  "status": "completed"
}

# 我们的方式（给 AI 看）
{
  "shared_context": {
    "step_1_keywords": [...],      # 裂变结果
    "step_2_notes": [...],         # 搜索结果
    "step_3_details": [...],       # 详情数据
    "step_4_analysis": {...}       # 分析结论
  },
  "logs": [                        # 完整执行链
    {"step": 1, "output": {...}},
    {"step": 2, "output": {...}},
    ...
  ]
}
```

### 4. **错误诊断**
```python
# Task 失败时，查看 logs 和 context
{
  "error": {"message": "Step 2 失败", "failed_step": 2},
  "shared_context": {
    "step_1_keywords": [...]  # Step 1 成功了，数据还在
  },
  "logs": [
    {"step": 1, "status": "completed"},
    {"step": 2, "status": "failed", "error": "..."}
  ]
}

# Agent 诊断：
# "Step 1 成功，Step 2 失败"
# "建议：检查 Step 2 的搜索逻辑，或使用 Step 1 的关键词重试"
```

---

## API 端点

| 端点 | 作用 | 返回 |
|------|------|------|
| `POST /sniper/trend` | 创建任务 | task_id, status |
| `GET /sniper/task/{id}` | 获取完整任务 | 所有上下文和日志 |
| `GET /sniper/task/{id}/logs` | 获取日志流 | 增量日志 |
| `POST /sniper/tasks` | 查询列表 | 任务摘要 |
| `DELETE /sniper/task/{id}` | 取消任务 | - |

---

## 与传统任务队列的区别

| 特性 | 传统任务队列 | 我们的 Task 模型 |
|------|------------|----------------|
| **目的** | 执行任务 | 记录记忆 + 提供上下文 |
| **数据** | 配置参数 | 执行过程 + 共享上下文 |
| **可见性** | 黑盒 | 透明（AI 可读） |
| **Agent 角色** | 不参与 | 查看历史，决定下一步 |
| **错误处理** | 重试或放弃 | AI 分析原因，智能恢复 |

---

## 总结

**核心就是一句话：**

> Task 表不是给调度器看的，是给 **AI 看的**。

AI 通过阅读 Task 的 `shared_context` 和 `logs`，就能理解：
1. 这个任务干了什么
2. 每一步的输入输出是什么
3. 现在进行到哪里了
4. 下一步该怎么走

这样，AI 就能真正参与到任务的执行和决策中，而不是只做一个黑盒执行器。
