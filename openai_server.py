#!/usr/bin/env python3
"""
OpenAI 风格的 HTTP API 服务端
支持常用的 OpenAI API 接口，如 chat/completions、models 等
"""

import os
import json
import time
import uuid
import asyncio
import logging
from typing import Optional, List, Dict, Any, AsyncGenerator
from datetime import datetime
from functools import wraps
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn

# 导入 AIStudioBot
from aistudio_bot import AIStudioBot

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 全局 AIStudioBot 实例
bot_instance: Optional[AIStudioBot] = None

# 会话管理：保存 conversation_id 到 prompt_id 的映射
# 格式: {conversation_id: {"prompt_id": str, "model": str, "created_at": int}}
conversation_sessions: Dict[str, Dict[str, Any]] = {}

# 会话存储文件路径
SESSIONS_FILE = os.path.join(os.path.dirname(__file__), 'conversation_sessions.json')


def load_sessions() -> None:
    """
    从磁盘加载会话映射
    """
    global conversation_sessions
    try:
        if os.path.exists(SESSIONS_FILE):
            with open(SESSIONS_FILE, 'r', encoding='utf-8') as f:
                conversation_sessions = json.load(f)
            logger.info(f"已加载 {len(conversation_sessions)} 个会话映射")
        else:
            conversation_sessions = {}
            logger.info("会话文件不存在，初始化为空")
    except Exception as e:
        logger.error(f"加载会话文件失败: {e}")
        conversation_sessions = {}


def persist_sessions() -> None:
    """
    将会话映射持久化到磁盘
    """
    try:
        with open(SESSIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(conversation_sessions, f, ensure_ascii=False, indent=2)
        logger.debug(f"已持久化 {len(conversation_sessions)} 个会话映射")
    except Exception as e:
        logger.error(f"持久化会话文件失败: {e}")


def get_conversation_prompt_id(conversation_id: str) -> Optional[str]:
    """
    获取会话对应的 prompt_id
    
    Args:
        conversation_id: OpenAI 风格的会话 ID
        
    Returns:
        str: Google AI Studio 的 prompt_id
        None: 会话不存在
    """
    session = conversation_sessions.get(conversation_id)
    return session.get("prompt_id") if session else None


def save_conversation_session(conversation_id: str, prompt_id: str, model: str) -> None:
    """
    保存会话信息并持久化到磁盘
    
    Args:
        conversation_id: OpenAI 风格的会话 ID
        prompt_id: Google AI Studio 的 prompt_id
        model: 使用的模型
    """
    conversation_sessions[conversation_id] = {
        "prompt_id": prompt_id,
        "model": model,
        "created_at": int(time.time())
    }
    logger.info(f"保存会话映射: {conversation_id} -> {prompt_id}")
    persist_sessions()


def delete_conversation_session(conversation_id: str) -> bool:
    """
    删除会话映射并持久化到磁盘
    
    Args:
        conversation_id: 要删除的会话ID
        
    Returns:
        bool: 是否成功删除
    """
    if conversation_id in conversation_sessions:
        del conversation_sessions[conversation_id]
        logger.info(f"删除会话映射: {conversation_id}")
        persist_sessions()
        return True
    return False


# ==================== 生命周期管理 ====================

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 应用生命周期管理
    启动时初始化 AIStudioBot，关闭时清理资源
    """
    global bot_instance
    
    logger.info("=" * 50)
    logger.info("正在初始化 AIStudioBot...")
    logger.info("=" * 50)
    
    # 加载持久化的会话映射
    load_sessions()
    
    try:
        # 从环境变量或配置中读取参数
        headless = os.getenv("BOT_HEADLESS", "true").lower() == "true"
        user_data_dir = os.getenv("BOT_USER_DATA_DIR")
        
        # 创建 AIStudioBot 实例
        bot_instance = AIStudioBot(
            headless=headless,
            user_data_dir=user_data_dir
        )
        
        # 启动浏览器
        bot_instance.start()
        
        # 执行登录流程
        logger.info("开始执行登录流程...")
        login_success = bot_instance.ensure_logged_in()
        
        if login_success:
            logger.info("=" * 50)
            logger.info("AIStudioBot 初始化完成，已登录")
            logger.info("=" * 50)


            list_models = bot_instance.get_available_models()
            if list_models:
                print(json.dumps(list_models, indent=2, ensure_ascii=False))
            else:
                # 获取任务类型选项
                task_options = bot_instance.get_task_type_options()
                print("可用任务类型:", task_options)
                
                # 通过 label 选择
                bot_instance.select_task_type("/chat")

                time.sleep(1)  # 等待模型下拉框出现
                model_options = bot_instance.get_model_options()
                print("可用模型:", model_options)

                # 更新模型缓存
                bot_instance._update_models_cache(model_options)

        else:
            logger.warning("=" * 50)
            logger.warning("AIStudioBot 初始化完成，但登录可能未完成")
            logger.warning("部分功能可能受限")
            logger.warning("=" * 50)
        
    except Exception as e:
        logger.error(f"AIStudioBot 初始化失败: {e}")
        bot_instance = None
    
    yield
    
    # 关闭时清理资源
    logger.info("正在关闭 AIStudioBot...")
    if bot_instance:
        try:
            bot_instance.quit()
            logger.info("AIStudioBot 已关闭")
        except Exception as e:
            logger.error(f"关闭 AIStudioBot 时出错: {e}")


# 创建 FastAPI 应用
app = FastAPI(
    title="OpenAI Compatible API Server with AIStudio",
    description="支持 OpenAI 风格的 API 接口服务端，集成 Google AI Studio",
    version="1.1.0",
    lifespan=lifespan
)

# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== 数据模型 ====================

class ChatMessage(BaseModel):
    """聊天消息模型"""
    role: str = Field(..., description="消息角色: system/user/assistant/tool")
    content: str = Field(..., description="消息内容")
    name: Optional[str] = Field(None, description="名称（用于 tool 消息）")


class ChatCompletionRequest(BaseModel):
    """聊天完成请求模型"""
    model: str = Field(..., description="模型名称")
    messages: List[ChatMessage] = Field(..., description="消息列表")
    temperature: Optional[float] = Field(0.7, ge=0, le=2, description="采样温度")
    top_p: Optional[float] = Field(1.0, ge=0, le=1, description="核采样")
    n: Optional[int] = Field(1, ge=1, le=10, description="生成数量")
    stream: Optional[bool] = Field(False, description="是否流式输出")
    stop: Optional[Any] = Field(None, description="停止序列")
    max_tokens: Optional[int] = Field(None, ge=1, description="最大生成token数")
    presence_penalty: Optional[float] = Field(0, ge=-2, le=2, description="存在惩罚")
    frequency_penalty: Optional[float] = Field(0, ge=-2, le=2, description="频率惩罚")
    logit_bias: Optional[Dict[str, float]] = Field(None, description="logit偏置")
    user: Optional[str] = Field(None, description="用户标识")
    conversation_id: Optional[str] = Field(None, description="会话ID，用于保持对话上下文")


class ChatCompletionChoice(BaseModel):
    """聊天完成选项模型"""
    index: int
    message: ChatMessage
    finish_reason: Optional[str] = None


class ChatCompletionChunkChoice(BaseModel):
    """流式聊天完成选项模型"""
    index: int
    delta: Dict[str, Any]
    finish_reason: Optional[str] = None


class UsageInfo(BaseModel):
    """用量信息模型"""
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


class ChatCompletionResponse(BaseModel):
    """聊天完成响应模型"""
    id: str
    object: str = "chat.completion"
    created: int
    model: str
    choices: List[ChatCompletionChoice]
    usage: UsageInfo


class ChatCompletionChunk(BaseModel):
    """流式聊天完成响应块模型"""
    id: str
    object: str = "chat.completion.chunk"
    created: int
    model: str
    choices: List[ChatCompletionChunkChoice]


class ModelInfo(BaseModel):
    """模型信息模型"""
    id: str
    object: str = "model"
    created: int
    owned_by: str
    display_name: Optional[str] = Field(None, description="模型显示名称")


class ModelsResponse(BaseModel):
    """模型列表响应模型"""
    object: str = "list"
    data: List[ModelInfo]


class EmbeddingRequest(BaseModel):
    """嵌入向量请求模型"""
    input: Any = Field(..., description="输入文本或文本列表")
    model: str = Field(..., description="模型名称")
    encoding_format: Optional[str] = Field("float", description="编码格式")
    dimensions: Optional[int] = Field(None, description="输出维度")
    user: Optional[str] = Field(None, description="用户标识")


class EmbeddingData(BaseModel):
    """嵌入向量数据模型"""
    object: str = "embedding"
    embedding: List[float]
    index: int


class EmbeddingResponse(BaseModel):
    """嵌入向量响应模型"""
    object: str = "list"
    data: List[EmbeddingData]
    model: str
    usage: UsageInfo


class BotStatusResponse(BaseModel):
    """Bot 状态响应模型"""
    initialized: bool
    page_available: bool
    current_url: Optional[str] = None
    page_title: Optional[str] = None


# ==================== 依赖注入 ====================

def get_bot() -> Optional[AIStudioBot]:
    """
    获取 AIStudioBot 实例的依赖函数
    在 API 路由中使用: bot: Optional[AIStudioBot] = Depends(get_bot)
    """
    return bot_instance


def require_bot() -> AIStudioBot:
    """
    要求 AIStudioBot 必须可用的依赖函数
    如果 bot 未初始化，抛出 HTTPException
    """
    if bot_instance is None:
        raise HTTPException(
            status_code=503,
            detail="AIStudioBot 未初始化或初始化失败，请检查服务状态"
        )
    return bot_instance


# ==================== 辅助函数 ====================

def generate_id(prefix: str = "chatcmpl") -> str:
    """生成唯一ID"""
    return f"{prefix}-{uuid.uuid4().hex[:24]}"


def get_timestamp() -> int:
    """获取当前时间戳"""
    return int(time.time())


def estimate_tokens(text: str) -> int:
    """估算token数量（简单估算：每4个字符约1个token）"""
    return len(text) // 4 + 1


async def send_message_to_bot(bot: AIStudioBot, model: str, message: str, conversation_id: Optional[str] = None) -> tuple[str, Optional[str]]:
    """
    使用 AIStudioBot 发送消息并获取响应
    实际调用 bot 的方法与 AI Studio 交互
    
    Args:
        bot: AIStudioBot 实例
        model: 模型名称
        message: 消息内容
        conversation_id: 会话ID，用于保持对话上下文
        
    Returns:
        tuple: (响应文本, prompt_id)
    """
    try:
        prompt_id = None
        
        # 如果有 conversation_id，尝试获取对应的 prompt_id
        if conversation_id:
            prompt_id = get_conversation_prompt_id(conversation_id)
        
        # 如果没有 prompt_id，需要创建新对话
        if not prompt_id:
            logger.info(f"创建新对话，模型: {model}")
            prompt_id = bot.create_new_chat(model, prompt=message)
            
            if not prompt_id:
                logger.error("创建新对话失败")
                return "[错误] 无法创建新对话", None
            
            # 保存会话映射
            if conversation_id:
                save_conversation_session(conversation_id, prompt_id, model)
            
            # 等待响应生成
            # TODO: 实现获取响应的逻辑
            # 这里需要等待 AI Studio 生成响应并获取内容
            await asyncio.sleep(5)  # 临时等待
            
            return "[响应内容待实现]", prompt_id
        else:
            # 使用现有对话发送消息
            logger.info(f"使用现有对话: {prompt_id}")
            success, current_prompt_id = bot.send_message(message, prompt_id=prompt_id)
            
            if not success:
                return "[错误] 发送消息失败", prompt_id
            
            # 如果 prompt_id 发生变化（例如对话分叉），更新映射
            if current_prompt_id and current_prompt_id != prompt_id and conversation_id:
                save_conversation_session(conversation_id, current_prompt_id, model)
                prompt_id = current_prompt_id
            
            # 等待响应生成
            await asyncio.sleep(5)  # 临时等待
            
            return "[响应内容待实现]", prompt_id
            
    except Exception as e:
        logger.error(f"调用 bot 发送消息失败: {e}")
        raise


async def generate_chat_stream_with_bot(
    bot: AIStudioBot,
    model: str,
    message: str,
    conversation_id: Optional[str] = None
) -> AsyncGenerator[str, None]:
    """
    使用 AIStudioBot 生成流式响应
    """
    response_id = generate_id()
    created = get_timestamp()
    
    try:
        # 发送消息并获取 prompt_id
        response_text, prompt_id = await send_message_to_bot(bot, model, message, conversation_id)
        
        # 如果 bot 支持流式输出
        if hasattr(bot, 'send_message_stream'):
            async for chunk in bot.send_message_stream(message, model=model):
                data = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta={"content": chunk},
                            finish_reason=None
                        )
                    ]
                )
                yield f"data: {json.dumps(data.model_dump(), ensure_ascii=False)}\n\n"
        else:
            # 非流式调用后分段返回
            # 模拟流式输出，每10个字符一个chunk
            chunk_size = 10
            for i in range(0, len(response_text), chunk_size):
                chunk = response_text[i:i + chunk_size]
                delta = {"content": chunk}
                if i == 0:
                    delta["role"] = "assistant"
                
                data = ChatCompletionChunk(
                    id=response_id,
                    created=created,
                    model=model,
                    choices=[
                        ChatCompletionChunkChoice(
                            index=0,
                            delta=delta,
                            finish_reason=None
                        )
                    ]
                )
                yield f"data: {json.dumps(data.model_dump(), ensure_ascii=False)}\n\n"
        
        # 发送结束标记
        final_data = ChatCompletionChunk(
            id=response_id,
            created=created,
            model=model,
            choices=[
                ChatCompletionChunkChoice(
                    index=0,
                    delta={},
                    finish_reason="stop"
                )
            ]
        )
        yield f"data: {json.dumps(final_data.model_dump(), ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"
        
    except Exception as e:
        logger.error(f"流式生成时出错: {e}")
        error_data = {
            "error": {
                "message": str(e),
                "type": "internal_error"
            }
        }
        yield f"data: {json.dumps(error_data)}\n\n"


# ==================== API 路由 ====================

@app.get("/")
async def root():
    """根路径，返回服务信息"""
    return {
        "message": "OpenAI Compatible API Server with AIStudio",
        "version": "1.1.0",
        "docs_url": "/docs",
        "endpoints": {
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models",
            "embeddings": "/v1/embeddings",
            "bot_status": "/v1/bot/status"
        }
    }


@app.get("/v1/bot/status", response_model=BotStatusResponse)
async def get_bot_status(bot: AIStudioBot = Depends(require_bot)):
    """
    获取 AIStudioBot 状态
    用于检查 bot 是否正常运行
    """
    try:
        page_available = bot.page is not None
        current_url = bot.page.url if page_available else None
        page_title = bot.page.title if page_available else None
        
        return BotStatusResponse(
            initialized=True,
            page_available=page_available,
            current_url=current_url,
            page_title=page_title
        )
    except Exception as e:
        logger.error(f"获取 bot 状态时出错: {e}")
        return BotStatusResponse(
            initialized=True,
            page_available=False,
            current_url=None,
            page_title=None
        )


@app.get("/v1/models", response_model=ModelsResponse)
async def list_models(bot: Optional[AIStudioBot] = Depends(get_bot)):
    """
    获取可用模型列表
    对应 OpenAI 的 GET /v1/models 接口
    如果 bot 可用，尝试从 AIStudio 获取真实模型列表
    """
    models = []
    
    # 尝试从 bot 获取模型列表
    if bot and hasattr(bot, 'get_available_models'):
        try:
            result = bot.get_available_models()
            if result and result.get('data'):
                for model_data in result['data']:
                    models.append(ModelInfo(
                        id=model_data.get('id', 'unknown'),
                        object="model",
                        created=model_data.get('created', get_timestamp()),
                        owned_by=model_data.get('owned_by', 'google'),
                        display_name=model_data.get('display_name')
                    ))
        except Exception as e:
            logger.warning(f"从 bot 获取模型列表失败: {e}")
    
    # 如果无法获取，返回错误信息
    if not models:
        raise HTTPException(
            status_code=503,
            detail="AIStudioBot初始化失败，无法获取模型列表"
        )
    
    return ModelsResponse(
        object="list",
        data=models
    )


@app.get("/v1/models/{model_id}")
async def get_model(model_id: str):
    """
    获取指定模型信息
    对应 OpenAI 的 GET /v1/models/{model} 接口
    """
    return ModelInfo(
        id=model_id,
        object="model",
        created=get_timestamp(),
        owned_by="google"
    )


@app.post("/v1/chat/completions")
async def chat_completions(
    request: ChatCompletionRequest,
    bot: AIStudioBot = Depends(require_bot)
):
    """
    创建聊天完成
    对应 OpenAI 的 POST /v1/chat/completions 接口
    支持流式和非流式输出，使用 AIStudioBot 调用真实的 Google AI Studio
    
    会话管理:
    - 如果提供了 conversation_id，会尝试使用已有的对话
    - 如果没有提供或对话不存在，会创建新对话
    """
    logger.info(f"Chat completion request: model={request.model}, stream={request.stream}, conversation_id={request.conversation_id}")
    
    try:
        # 构建用户消息
        user_message = ""
        for msg in request.messages:
            if msg.role == "system":
                user_message += f"[System]: {msg.content}\n"
            elif msg.role == "user":
                user_message += f"{msg.content}\n"
        
        user_message = user_message.strip()
        
        # 生成或获取会话ID
        conversation_id = request.conversation_id or generate_id("conv")
        
        if request.stream:
            # 流式响应
            return StreamingResponse(
                generate_chat_stream_with_bot(bot, request.model, user_message, conversation_id),
                media_type="text/event-stream"
            )
        else:
            # 非流式响应 - 调用 bot 发送消息
            response_text, prompt_id = await send_message_to_bot(bot, request.model, user_message, conversation_id)
            
            prompt_tokens = sum(estimate_tokens(msg.content) for msg in request.messages)
            completion_tokens = estimate_tokens(response_text)
            
            response = ChatCompletionResponse(
                id=generate_id(),
                created=get_timestamp(),
                model=request.model,
                choices=[
                    ChatCompletionChoice(
                        index=0,
                        message=ChatMessage(
                            role="assistant",
                            content=response_text
                        ),
                        finish_reason="stop"
                    )
                ],
                usage=UsageInfo(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=prompt_tokens + completion_tokens
                )
            )
            
            # 在响应头中添加会话信息
            response_data = response.model_dump()
            response_data["conversation_id"] = conversation_id
            
            return JSONResponse(content=response_data)
            
    except Exception as e:
        logger.error(f"Error in chat completion: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/v1/completions")
async def create_completion(request: Request):
    """
    创建文本完成（传统接口）
    对应 OpenAI 的 POST /v1/completions 接口
    """
    body = await request.json()
    logger.info(f"Completion request: {body.get('model', 'unknown')}")
    
    # 将传统 completion 转换为 chat completion 格式
    prompt = body.get("prompt", "")
    model = body.get("model", "gpt-3.5-turbo-instruct")
    
    # 构建模拟响应
    response_text = f"这是一个模拟的文本完成响应。Prompt: {prompt[:50]}..."
    
    return JSONResponse(content={
        "id": generate_id("cmpl"),
        "object": "text_completion",
        "created": get_timestamp(),
        "model": model,
        "choices": [
            {
                "text": response_text,
                "index": 0,
                "logprobs": None,
                "finish_reason": "stop"
            }
        ],
        "usage": {
            "prompt_tokens": estimate_tokens(prompt),
            "completion_tokens": estimate_tokens(response_text),
            "total_tokens": estimate_tokens(prompt) + estimate_tokens(response_text)
        }
    })

@app.get("/v1/sessions")
async def list_sessions():
    """
    列出所有活跃的会话
    
    Returns:
        dict: 会话列表，包含 conversation_id 到 prompt_id 的映射
    """
    return {
        "object": "list",
        "data": [
            {
                "conversation_id": conv_id,
                "prompt_id": session["prompt_id"],
                "model": session["model"],
                "created_at": session["created_at"]
            }
            for conv_id, session in conversation_sessions.items()
        ]
    }


@app.get("/v1/sessions/{conversation_id}")
async def get_session(conversation_id: str):
    """
    获取指定会话的详细信息
    
    Args:
        conversation_id: 会话ID
        
    Returns:
        dict: 会话信息，包括 prompt_id 和对话链接
    """
    session = conversation_sessions.get(conversation_id)
    if not session:
        raise HTTPException(status_code=404, detail="会话不存在")
    
    prompt_id = session["prompt_id"]
    chat_url = f"https://aistudio.google.com/prompts/{prompt_id}"
    
    return {
        "conversation_id": conversation_id,
        "prompt_id": prompt_id,
        "model": session["model"],
        "created_at": session["created_at"],
        "chat_url": chat_url
    }


@app.delete("/v1/sessions/{conversation_id}")
async def delete_session(conversation_id: str):
    """
    删除指定的会话映射
    
    Args:
        conversation_id: 会话ID
        
    Returns:
        dict: 删除结果
    """
    if delete_conversation_session(conversation_id):
        return {"deleted": True, "conversation_id": conversation_id}
    else:
        raise HTTPException(status_code=404, detail="会话不存在")


# ==================== 启动入口 ====================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenAI Compatible API Server with AIStudio")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    parser.add_argument("--headless", type=lambda x: x.lower() == "true", 
                        default=True, help="Bot 无头模式 (默认: true)")
    parser.add_argument("--user-data-dir", help="Bot 用户数据目录")
    parser.add_argument("--cookie-file", help="Bot cookie 文件路径")
    
    args = parser.parse_args()
    
    # 设置环境变量供 lifespan 使用
    os.environ["BOT_HEADLESS"] = str(args.headless).lower()
    if args.user_data_dir:
        os.environ["BOT_USER_DATA_DIR"] = args.user_data_dir
    if args.cookie_file:
        os.environ["BOT_COOKIE_FILE"] = args.cookie_file
    
    logger.info("=" * 50)
    logger.info(f"Starting OpenAI Compatible API Server")
    logger.info(f"Host: {args.host}, Port: {args.port}")
    logger.info(f"API documentation: http://{args.host}:{args.port}/docs")
    logger.info("=" * 50)
    
    uvicorn.run(
        "openai_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()


# ==================== 主函数 ====================

def main():
    """启动服务端"""
    import argparse
    
    parser = argparse.ArgumentParser(description="OpenAI Compatible API Server with AIStudio")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址 (默认: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="监听端口 (默认: 8000)")
    parser.add_argument("--reload", action="store_true", help="启用热重载（开发模式）")
    parser.add_argument("--headless", type=lambda x: x.lower() == "true", 
                        default=True, help="Bot 无头模式 (默认: true)")
    parser.add_argument("--user-data-dir", help="Bot 用户数据目录")
    parser.add_argument("--cookie-file", help="Bot cookie 文件路径")
    
    args = parser.parse_args()
    
    # 设置环境变量供 lifespan 使用
    os.environ["BOT_HEADLESS"] = str(args.headless).lower()
    if args.user_data_dir:
        os.environ["BOT_USER_DATA_DIR"] = args.user_data_dir
    if args.cookie_file:
        os.environ["BOT_COOKIE_FILE"] = args.cookie_file
    
    logger.info("=" * 50)
    logger.info(f"Starting OpenAI Compatible API Server")
    logger.info(f"Host: {args.host}, Port: {args.port}")
    logger.info(f"API documentation: http://{args.host}:{args.port}/docs")
    logger.info("=" * 50)
    
    uvicorn.run(
        "openai_server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="info"
    )


if __name__ == "__main__":
    main()
