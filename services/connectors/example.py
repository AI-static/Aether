"""
连接器使用示例 - 展示四大核心功能的用法

功能说明：
1. 提取 (extract): 一次性获取指定URL的内容
2. 监控 (monitor): 持续追踪URL变化，实时推送更新
3. 采收 (harvest): 批量获取用户/账号的所有内容
4. 发布 (publish): 发布内容到平台
"""

import asyncio
from services.connectors import connector_service


async def example_extract():
    """示例1：提取内容 - 自动检测平台"""
    print("=== 示例1：提取内容 ===")

    urls = [
        "https://www.xiaohongshu.com/explore/xxx",
        "https://mp.weixin.qq.com/s/xxx",
        "https://example.com/page"  # 通用网站
    ]

    # 自动检测平台并提取
    results = await connector_service.extract_urls(urls)

    for result in results:
        print(f"\nURL: {result['url']}")
        print(f"成功: {result['success']}")
        if result['success']:
            print(f"数据: {result['data']}")
        else:
            print(f"错误: {result.get('error', 'Unknown error')}")


async def example_extract_with_instruction():
    """示例2：提取内容 - 使用自定义提取指令"""
    print("\n=== 示例2：自定义提取指令 ===")

    results = await connector_service.extract_urls(
        urls=["https://www.xiaohongshu.com/explore/xxx"],
        instruction="只提取标题、作者名称和点赞数"
    )

    for result in results:
        print(f"提取结果: {result['data']}")


async def example_extract_with_schema():
    """示例3：提取内容 - 使用结构化 Schema"""
    print("\n=== 示例3：结构化数据提取 ===")

    # 定义数据结构
    schema = {
        "title": "string",
        "author": "string",
        "like_count": "number",
        "content": "string"
    }

    results = await connector_service.extract_urls(
        urls=["https://www.xiaohongshu.com/explore/xxx"],
        schema=schema
    )

    for result in results:
        print(f"结构化数据: {result['data']}")


async def example_monitor():
    """示例4：监控URL变化"""
    print("\n=== 示例4：监控URL ===")

    urls = [
        "https://www.xiaohongshu.com/explore/xxx",
        "https://mp.weixin.qq.com/s/xxx"
    ]

    # 监控变化（每60秒检查一次）
    count = 0
    async for change in connector_service.monitor_urls(urls, check_interval=60):
        print(f"\n检测到变化:")
        print(f"  URL: {change['url']}")
        print(f"  类型: {change['type']}")
        print(f"  变化: {change['changes']}")

        count += 1
        if count >= 3:  # 演示用，只检测3次
            break


async def example_harvest():
    """示例5：采收用户内容"""
    print("\n=== 示例5：采收用户内容 ===")

    # 采收小红书用户的笔记
    notes = await connector_service.harvest_user_content(
        platform="xiaohongshu",
        user_id="5e8d7c9b000000000100000a",  # 示例用户ID
        limit=10
    )

    print(f"采收到 {len(notes)} 条笔记:")
    for note in notes[:3]:  # 只显示前3条
        print(f"  - {note.get('title', 'No title')}")


async def example_harvest_wechat():
    """示例6：采收微信公众号文章"""
    print("\n=== 示例6：采收公众号文章 ===")

    # 采收公众号文章
    articles = await connector_service.harvest_user_content(
        platform="wechat",
        user_id="MzI1MTUxMDY0MA==",  # 公众号的 __biz 参数
        limit=20
    )

    print(f"采收到 {len(articles)} 篇文章:")
    for article in articles[:3]:
        print(f"  - {article.get('title', 'No title')}")


async def example_publish():
    """示例7：发布内容（需要先登录）"""
    print("\n=== 示例7：发布内容 ===")

    # 先登录小红书
    login_success = await connector_service.login(
        platform="xiaohongshu",
        method="cookie",
        cookies={
            "web_session": "your_web_session_here",
            "webId": "your_webId_here"
        }
    )

    if not login_success:
        print("登录失败，跳过发布")
        return

    # 发布文字笔记
    result = await connector_service.publish_content(
        platform="xiaohongshu",
        content="这是一条测试笔记的内容",
        content_type="text",
        tags=["测试", "示例"]
    )

    print(f"发布结果: {result}")


async def example_publish_image():
    """示例8：发布图文内容"""
    print("\n=== 示例8：发布图文 ===")

    result = await connector_service.publish_content(
        platform="xiaohongshu",
        content="分享一些美图",
        content_type="image",
        images=[
            "https://example.com/image1.jpg",
            "https://example.com/image2.jpg"
        ],
        tags=["摄影", "分享"]
    )

    print(f"发布结果: {result}")


async def example_multiple_platforms():
    """示例9：同时处理多个平台"""
    print("\n=== 示例9：多平台混合 ===")

    # 混合不同平台的URL，自动分组处理
    mixed_urls = [
        "https://www.xiaohongshu.com/explore/aaa",
        "https://www.xiaohongshu.com/explore/bbb",
        "https://mp.weixin.qq.com/s/xxx",
        "https://mp.weixin.qq.com/s/yyy",
        "https://example.com/page1",
    ]

    results = await connector_service.extract_urls(mixed_urls)

    # 按平台统计
    platforms = {}
    for result in results:
        # 通过URL判断平台
        if "xiaohongshu" in result['url']:
            platform = "xiaohongshu"
        elif "weixin" in result['url']:
            platform = "wechat"
        else:
            platform = "generic"

        if platform not in platforms:
            platforms[platform] = 0
        platforms[platform] += 1

    print("处理结果统计:")
    for platform, count in platforms.items():
        print(f"  {platform}: {count} 条")


async def main():
    """运行所有示例"""
    examples = [
        ("提取内容", example_extract),
        ("自定义提取指令", example_extract_with_instruction),
        ("结构化数据提取", example_extract_with_schema),
        ("监控URL", example_monitor),
        ("采收用户内容", example_harvest),
        ("采收公众号文章", example_harvest_wechat),
        ("发布内容", example_publish),
        ("发布图文", example_publish_image),
        ("多平台混合", example_multiple_platforms),
    ]

    print("连接器使用示例")
    print("=" * 50)

    for i, (name, func) in enumerate(examples, 1):
        print(f"\n[{i}/{len(examples)}] {name}")
        try:
            await func()
        except Exception as e:
            print(f"示例执行出错: {e}")

        if i < len(examples):
            print("\n" + "-" * 50)

    print("\n示例运行完成")


if __name__ == "__main__":
    # 运行所有示例
    # asyncio.run(main())

    # 或者运行单个示例
    asyncio.run(example_extract())
