"""Agent服务"""
from typing import List, Dict, Any
from models.images import IMAGE_MODELS
from config.settings import settings


# Agno imports
from agno.agent import Agent
from agno.memory import MemoryManager
from agno.models.openai import OpenAIChat
from agno.tools import tool
from agno.db.postgres import PostgresDb

db = PostgresDb(
    db_url=f"postgresql+psycopg://{settings.database.user}:{settings.database.password}@{settings.database.host}:{settings.database.port}/{settings.database.name}"
)

memory_manager = MemoryManager(
    db=db,
    # Select the model used for memory creation and updates. If unset, the default model of the Agent is used.
    model=OpenAIChat(base_url=settings.external_service.vectorai_base_url, api_key=settings.external_service.vectorai_api_key,id="gpt-5-mini"),
    # You can also provide additional instructions
    additional_instructions="Don't store the user's real name",
)

# 图像生成工具
@tool()
def generate_image(
    prompt: str, 
    style: str = "realistic",
    model: str = "gemini-2.5-flash-image-preview",
    size: str = "1024x1024"
) -> Dict[str, Any]:
    """
    生成图像工具
    
    Args:
        prompt (str): 图像描述
        style (str): 艺术风格 (realistic, anime, oil_painting, watercolor, sketch)
        model (str): 生成模型
        size (str): 图像尺寸
        
    Returns:
        dict: 生成结果
    """
    # 根据风格增强提示词
    style_prompts = {
        "realistic": "photorealistic, high detail, 8k resolution",
        "anime": "anime style, manga, Japanese animation",
        "oil_painting": "oil painting, classical art technique",
        "watercolor": "watercolor painting, soft colors",
        "sketch": "pencil sketch, black and white"
    }
    
    style_prefix = style_prompts.get(style, "")
    enhanced_prompt = f"{style_prefix}, {prompt}" if style_prefix else prompt
    
    # 这里返回增强后的提示词，实际调用在异步函数中
    return {
        "success": True,
        "style": style,
        "enhanced_prompt": enhanced_prompt,
        "prompt": prompt,
        "model": model,
        "size": size,
        "message": "图像生成请求已处理"
    }



class DrawingAgent:
    """画图Agent"""
    
    def __init__(self, source_id: str = None):
        """
        初始化画图Agent
        
        Args:
            source_id: 来源ID，用于会话管理
        """
        self.source_id = source_id
        # 创建Agno Agent
        self.agent = Agent(
            name="Drawing Assistant",
            model=OpenAIChat(id="gpt-4"),
            tools=[generate_image],
            instructions=f"""
            你是一个专业的AI绘画助手，可以帮助用户：
            1. 根据文字描述生成图像
            2. 推荐合适的绘画风格和参数
            3. 记住用户的偏好和之前的对话历史
            
            当用户要求生成图像时，请使用 generate_image 工具。
            支持的风格包括：realistic（写实）、anime（动漫）、oil_painting（油画）、watercolor（水彩）、sketch（素描）
            支持的模型详情：{IMAGE_MODELS}
            
            请根据用户的需求和之前的对话历史，选择合适的风格、模型和尺寸。
            记住用户的偏好，以便下次提供更好的服务。
            
            当前会话ID: {source_id or 'default'}
            """,
            markdown=True,
            add_history_to_context=True,
            user_id=source_id,
            memory_manager=memory_manager
        )
