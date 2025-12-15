"""
WebSocket 监控客户端示例

演示如何使用 /connectors/monitor WebSocket 端点实时监控URL变化
"""

import asyncio
import json
import websockets


async def monitor_urls():
    """连接到监控 WebSocket 并接收实时更新"""

    # WebSocket 服务器地址
    uri = "ws://localhost:8000/connectors/monitor"

    # 监控配置
    monitor_config = {
        "urls": [
            "https://www.xiaohongshu.com/explore/123456",
            "https://mp.weixin.qq.com/s/abcdefg"
        ],
        "platform": None,  # 自动检测平台
        "check_interval": 60,  # 每60秒检查一次
        "webhook_url": None  # 可选的webhook回调
    }

    try:
        async with websockets.connect(uri) as websocket:
            print(f"✓ 已连接到监控服务: {uri}")

            # 1. 发送监控配置
            print(f"\n发送监控配置:")
            print(json.dumps(monitor_config, indent=2, ensure_ascii=False))
            await websocket.send(json.dumps(monitor_config))

            # 2. 接收并处理消息
            print(f"\n等待监控事件...\n")

            async for message in websocket:
                data = json.loads(message)
                msg_type = data.get("type")

                if msg_type == "ack":
                    # 监控启动确认
                    print("✓ 监控已启动")
                    print(f"  监控URL数量: {data['config']['url_count']}")
                    print(f"  检查间隔: {data['config']['check_interval']}秒")
                    print(f"  平台: {data['config']['platform'] or '自动检测'}")
                    print()

                elif msg_type == "change":
                    # 检测到变化
                    change_data = data["data"]
                    print(f"🔔 检测到变化!")
                    print(f"  URL: {change_data.get('url')}")
                    print(f"  类型: {change_data.get('type')}")
                    print(f"  时间戳: {change_data.get('timestamp')}")

                    # 打印具体变化内容
                    changes = change_data.get("changes", {})
                    if changes:
                        print(f"  变化详情:")
                        for key, value in changes.items():
                            print(f"    {key}:")
                            print(f"      旧值: {value.get('old')}")
                            print(f"      新值: {value.get('new')}")
                    print()

                elif msg_type == "error":
                    # 错误消息
                    print(f"✗ 错误: {data.get('message')}")
                    if "detail" in data:
                        print(f"  详情: {data['detail']}")
                    break

    except websockets.exceptions.ConnectionClosed:
        print("\n✗ 连接已关闭")
    except KeyboardInterrupt:
        print("\n✓ 用户中断")
    except Exception as e:
        print(f"\n✗ 发生错误: {e}")


async def monitor_single_url():
    """监控单个URL的简单示例"""
    uri = "ws://localhost:8000/connectors/monitor"

    config = {
        "urls": ["https://www.xiaohongshu.com/explore/123456"],
        "platform": "xiaohongshu",
        "check_interval": 30
    }

    async with websockets.connect(uri) as ws:
        await ws.send(json.dumps(config))

        async for message in ws:
            data = json.loads(message)
            if data["type"] == "change":
                print(f"变化: {data['data']['url']}")


if __name__ == "__main__":
    print("=" * 60)
    print("WebSocket 监控客户端")
    print("=" * 60)

    # 运行监控
    asyncio.run(monitor_urls())

    # 或者使用简单版本:
    # asyncio.run(monitor_single_url())
