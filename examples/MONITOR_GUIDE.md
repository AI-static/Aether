# Connectors 监控功能使用指南

## WebSocket 监控端点

### 端点地址
```
ws://your-server:8000/connectors/monitor
```

### 工作流程

1. **建立连接** - 客户端连接到 WebSocket 端点
2. **发送配置** - 客户端发送监控配置 JSON
3. **接收确认** - 服务器返回启动确认消息
4. **实时推送** - 服务器检测到变化时实时推送事件
5. **断开连接** - 客户端或服务器主动关闭连接

---

## 消息格式

### 1. 客户端 → 服务器：监控配置

```json
{
  "urls": [
    "https://www.xiaohongshu.com/explore/123456",
    "https://mp.weixin.qq.com/s/abcdefg"
  ],
  "platform": null,
  "check_interval": 60,
  "webhook_url": null
}
```

**字段说明:**
- `urls` (必需): 要监控的URL列表
- `platform` (可选): 平台名称 (`xiaohongshu`/`wechat`/`generic`)，不指定则自动检测
- `check_interval` (可选): 检查间隔（秒），默认 3600
- `webhook_url` (可选): 可选的 webhook 回调地址

### 2. 服务器 → 客户端：确认消息 (ack)

```json
{
  "type": "ack",
  "message": "监控已启动",
  "config": {
    "urls": ["..."],
    "platform": "xiaohongshu",
    "check_interval": 60,
    "url_count": 2
  }
}
```

### 3. 服务器 → 客户端：变化事件 (change)

```json
{
  "type": "change",
  "data": {
    "url": "https://www.xiaohongshu.com/explore/123456",
    "type": "content_changed",
    "changes": {
      "title": {
        "old": "旧标题",
        "new": "新标题"
      },
      "likes_count": {
        "old": 100,
        "new": 150
      }
    },
    "timestamp": 1702345678.123
  },
  "timestamp": 1702345678.123
}
```

### 4. 服务器 → 客户端：错误消息 (error)

```json
{
  "type": "error",
  "code": 400,
  "message": "配置验证失败",
  "detail": "urls field required"
}
```

---

## 使用示例

### Python 客户端

```bash
# 安装依赖
pip install websockets

# 运行示例
python examples/monitor_client.py
```

**代码示例:**
```python
import asyncio
import json
import websockets

async def monitor():
    uri = "ws://localhost:8000/connectors/monitor"

    config = {
        "urls": ["https://www.xiaohongshu.com/explore/123"],
        "check_interval": 60
    }

    async with websockets.connect(uri) as ws:
        # 发送配置
        await ws.send(json.dumps(config))

        # 接收事件
        async for message in ws:
            data = json.loads(message)
            if data["type"] == "change":
                print(f"检测到变化: {data['data']['url']}")

asyncio.run(monitor())
```

### JavaScript/浏览器客户端

```bash
# 直接在浏览器中打开
examples/monitor_client.html
```

**代码示例:**
```javascript
const ws = new WebSocket('ws://localhost:8000/connectors/monitor');

ws.onopen = () => {
    // 发送配置
    ws.send(JSON.stringify({
        urls: ['https://www.xiaohongshu.com/explore/123'],
        check_interval: 60
    }));
};

ws.onmessage = (event) => {
    const data = JSON.parse(event.data);

    if (data.type === 'ack') {
        console.log('监控已启动');
    } else if (data.type === 'change') {
        console.log('检测到变化:', data.data);
    }
};
```

### curl 测试 (HTTP 接口)

除了 WebSocket，你也可以使用 HTTP POST 接口进行一次性提取：

```bash
# 提取内容
curl -X POST http://localhost:8000/connectors/extract \
  -H "Content-Type: application/json" \
  -d '{
    "urls": ["https://www.xiaohongshu.com/explore/123"],
    "platform": "xiaohongshu"
  }'

# 采收用户内容
curl -X POST http://localhost:8000/connectors/harvest \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "xiaohongshu",
    "user_id": "user123",
    "limit": 10
  }'

# 发布内容
curl -X POST http://localhost:8000/connectors/publish \
  -H "Content-Type: application/json" \
  -d '{
    "platform": "xiaohongshu",
    "content": "测试内容",
    "tags": ["测试"]
  }'
```

---

## 为什么使用 yield (异步生成器)?

### 1. **实时推送**
`yield` 允许在检测到变化时立即推送，无需等待所有监控结束：

```python
# 使用 yield - 实时推送
async for change in monitor_urls(urls):
    yield change  # 立即返回

# 不用 yield - 需要等很久
results = []
# ... 监控很久 ...
return results  # 等所有完成才返回
```

### 2. **内存效率**
监控可能持续数小时产生大量事件，`yield` 只保存当前事件：

```python
while True:  # 无限循环
    if has_change:
        yield change  # 用完即丢，不占内存
    await asyncio.sleep(3600)
```

### 3. **无限数据流**
监控是永不停止的循环 (`while True`)，`yield` 创建无限事件流：

```python
while True:  # 永不停止
    yield change  # 源源不断产生
```

### 4. **灵活控制**
调用方可随时停止接收：

```python
async for change in monitor_urls(urls):
    print(change)
    if should_stop:
        break  # 随时退出
```

---

## 架构说明

```
┌─────────────┐         WebSocket          ┌──────────────────┐
│   客户端     │ ◄────────────────────────► │  /monitor 端点   │
└─────────────┘                             └──────────────────┘
                                                     │
                                                     ▼
                                            ┌──────────────────┐
                                            │ connector_service │
                                            └──────────────────┘
                                                     │
                           ┌─────────────────────────┼──────────────────┐
                           ▼                         ▼                  ▼
                    ┌──────────────┐        ┌──────────────┐   ┌──────────────┐
                    │ xiaohongshu  │        │    wechat    │   │   generic    │
                    │  connector   │        │  connector   │   │  connector   │
                    └──────────────┘        └──────────────┘   └──────────────┘
                           │                         │                  │
                           └─────────────────────────┴──────────────────┘
                                                     │
                                            使用 yield 实时推送
                                            async for change in monitor()
```

---

## 错误处理

| 错误类型 | HTTP 状态码 | 说明 |
|---------|-----------|------|
| `VALIDATION_ERROR` | 400 | 配置参数验证失败 |
| `BAD_REQUEST` | 400 | 无效的JSON或参数错误 |
| `INTERNAL_ERROR` | 500 | 服务器内部错误 |

---

## 注意事项

1. **连接超时**: WebSocket 可能因网络问题断开，客户端应实现重连机制
2. **检查间隔**: `check_interval` 不宜过小（建议 ≥30秒），避免频繁请求
3. **内存管理**: 监控大量URL时注意服务器内存使用
4. **并发限制**: 建议单个连接监控的URL数量不超过50个

---

## 完整 API 列表

| 端点 | 方法 | 说明 |
|-----|------|------|
| `/connectors/extract` | POST | 提取URL内容 |
| `/connectors/monitor` | WebSocket | 实时监控URL变化 |
| `/connectors/harvest` | POST | 采收用户内容 |
| `/connectors/publish` | POST | 发布内容 |
| `/connectors/login` | POST | 登录平台 |
| `/connectors/platforms` | GET | 获取支持的平台列表 |
