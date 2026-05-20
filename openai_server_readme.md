# OpenAI Compatible API Server with AIStudio

基于 FastAPI 的 OpenAI 风格 API 服务端，集成 Google AI Studio 自动化功能。

## 功能特性

- ✅ OpenAI 兼容的 API 接口 (`/v1/chat/completions`, `/v1/models` 等)
- ✅ 集成 AIStudioBot，支持 Google AI Studio 自动化操作
- ✅ 支持流式和非流式聊天响应
- ✅ 自动浏览器生命周期管理（启动/关闭）
- ✅ CORS 跨域支持
- ✅ 交互式 API 文档 (Swagger UI)

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 启动服务

```bash
# 基本启动
python openai_server.py

# 指定端口
python openai_server.py --port 8080

# 非无头模式（显示浏览器窗口，便于调试）
python openai_server.py --headless false

# 指定用户数据目录和 Cookie 文件
python openai_server.py --user-data-dir ./bot_data --cookie-file ./cookies.json

# 开发模式（启用热重载，代码修改后自动重启）
uvicorn openai_server:app --reload --host 0.0.0.0 --port 8000

# 开发模式 + 非无头模式（通过环境变量配置）
BOT_HEADLESS=false uvicorn openai_server:app --reload --host 0.0.0.0 --port 8000

# 开发模式 + 完整环境变量配置
BOT_HEADLESS=false BOT_USER_DATA_DIR=./bot_data BOT_COOKIE_FILE=./cookies.json uvicorn openai_server:app --reload --host 0.0.0.0 --port 8000
```

### 3. 环境变量配置

| 环境变量 | 说明 | 默认值 |
|---------|------|--------|
| `BOT_HEADLESS` | 是否启用无头模式 | `true` |
| `BOT_USER_DATA_DIR` | 浏览器用户数据目录 | `None` |
| `BOT_COOKIE_FILE` | Cookie 文件路径 | `aistudio_cookies.json` |
| `GOOGLE_EMAIL` | Google 账号邮箱 | `None` |
| `GOOGLE_PASSWORD` | Google 账号密码 | `None` |
| `HTTP_PROXY` / `http_proxy` | HTTP 代理地址（大小写兼容） | `None` |
| `HTTPS_PROXY` / `https_proxy` | HTTPS 代理地址（大小写兼容，优先使用） | `None` |

## API 接口文档

### 基础信息

- 服务地址: `http://localhost:8000`
- API 文档: `http://localhost:8000/docs` (Swagger UI)
- 备用文档: `http://localhost:8000/redoc` (ReDoc)

### 接口列表

#### 1. 根路径

```http
GET /
```

返回服务基本信息。

**响应示例:**
```json
{
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
```

#### 2. 获取 Bot 状态

```http
GET /v1/bot/status
```

获取 AIStudioBot 运行状态。

**响应示例:**
```json
{
  "initialized": true,
  "page_available": true,
  "current_url": "https://aistudio.google.com/app/apps/drive/...",
  "page_title": "Google AI Studio"
}
```

#### 3. 获取模型列表

```http
GET /v1/models
```

获取可用的模型列表。

**响应示例:**
```json
{
  "object": "list",
  "data": [
    {
      "id": "gemini-2.5-pro-exp-03-25",
      "object": "model",
      "created": 1700000000,
      "owned_by": "google"
    },
    {
      "id": "gemini-2.0-flash",
      "object": "model",
      "created": 1700000000,
      "owned_by": "google"
    }
  ]
}
```

#### 4. 聊天完成 (Chat Completions)

```http
POST /v1/chat/completions
```

创建聊天完成请求，支持流式和非流式响应。

**请求参数:**

| 参数 | 类型 | 必填 | 说明 |
|-----|------|-----|------|
| `model` | string | 是 | 模型名称，如 `gemini-2.0-flash` |
| `messages` | array | 是 | 消息列表 |
| `stream` | boolean | 否 | 是否流式输出，默认 `false` |
| `temperature` | float | 否 | 采样温度，范围 0-2，默认 `0.7` |
| `max_tokens` | integer | 否 | 最大生成 token 数 |

**请求示例:**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [
      {"role": "system", "content": "你是一个有帮助的助手"},
      {"role": "user", "content": "你好，请介绍一下自己"}
    ],
    "temperature": 0.7
  }'
```

**响应示例 (非流式):**

```json
{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1700000000,
  "model": "gemini-2.0-flash",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "你好！我是 Gemini，一个 AI 助手..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 50,
    "total_tokens": 75
  }
}
```

**流式响应示例:**

```bash
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

响应格式为 SSE (Server-Sent Events):

```
data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gemini-2.0-flash","choices":[{"index":0,"delta":{"role":"assistant"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gemini-2.0-flash","choices":[{"index":0,"delta":{"content":"你好"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gemini-2.0-flash","choices":[{"index":0,"delta":{"content":"！"},"finish_reason":null}]}

data: {"id":"chatcmpl-xxx","object":"chat.completion.chunk","created":1700000000,"model":"gemini-2.0-flash","choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}

data: [DONE]
```

## 客户端使用示例

### Python (使用 OpenAI 官方库)

``python
import openai

# 配置客户端
client = openai.OpenAI(
    base_url="http://localhost:8000/v1",
    api_key="sk-fake-key"  # 任意值，服务端不验证
)

# 非流式聊天
response = client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[
        {"role": "system", "content": "你是一个有帮助的助手"},
        {"role": "user", "content": "你好"}
    ]
)
print(response.choices[0].message.content)

# 流式聊天
for chunk in client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[{"role": "user", "content": "你好"}],
    stream=True
):
    content = chunk.choices[0].delta.content
    if content:
        print(content, end="")

# 获取模型列表
models = client.models.list()
for model in models.data:
    print(model.id)

# 创建嵌入
embedding = client.embeddings.create(
    input="Hello world",
    model="text-embedding-3-small"
)
print(embedding.data[0].embedding)
```

### JavaScript/TypeScript

```
// 非流式请求
const response = await fetch('http://localhost:8000/v1/chat/completions', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    model: 'gemini-2.0-flash',
    messages: [{ role: 'user', content: '你好' }],
  }),
});

const data = await response.json();
console.log(data.choices[0].message.content);

// 流式请求
const eventSource = new EventSource(
  'http://localhost:8000/v1/chat/completions?' +
  new URLSearchParams({
    model: 'gemini-2.0-flash',
    messages: JSON.stringify([{ role: 'user', content: '你好' }]),
    stream: 'true',
  })
);

eventSource.onmessage = (event) => {
  if (event.data === '[DONE]') {
    eventSource.close();
    return;
  }
  const chunk = JSON.parse(event.data);
  const content = chunk.choices[0].delta.content;
  if (content) {
    process.stdout.write(content);
  }
};
```

### cURL

```
# 查看服务状态
curl http://localhost:8000/

# 查看 Bot 状态
curl http://localhost:8000/v1/bot/status

# 获取模型列表
curl http://localhost:8000/v1/models

# 非流式聊天
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [{"role": "user", "content": "你好"}]
  }'

# 流式聊天
curl -X POST http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "gemini-2.0-flash",
    "messages": [{"role": "user", "content": "你好"}],
    "stream": true
  }'
```

## 命令行参数

```
python openai_server.py --help
```

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| `--host` | string | `0.0.0.0` | 监听地址 |
| `--port` | int | `8000` | 监听端口 |
| `--reload` | flag | `false` | 启用热重载（开发模式） |
| `--headless` | bool | `true` | Bot 无头模式 |
| `--user-data-dir` | string | `None` | 浏览器用户数据目录 |
| `--cookie-file` | string | `None` | Cookie 文件路径 |

## 项目结构

```
.
├── openai_server.py          # 主服务端文件
├── aistudio_bot.py           # AIStudioBot 自动化类
├── requirements.txt          # 依赖列表
└── openai_server_readme.md   # 本文档
```

## 注意事项

1. **首次启动**: 首次启动时会自动打开浏览器并访问 Google AI Studio，可能需要手动完成登录流程。

2. **Cookie 持久化**: 登录成功后会自动保存 Cookie，下次启动时会尝试恢复登录状态。

3. **无头模式**: 生产环境建议使用 `--headless true`（默认），调试时可使用 `--headless false` 查看浏览器窗口。

4. **网络代理**: 通过环境变量配置代理，同时兼容大小写（`HTTP_PROXY`/`http_proxy`, `HTTPS_PROXY`/`https_proxy`），`HTTPS_PROXY`/`https_proxy` 优先级更高。例如：
   ```bash
   # 小写格式（Linux/macOS 常用）
   export http_proxy="http://127.0.0.1:7890"
   export https_proxy=$http_proxy
   python openai_server.py
   
   # 大写格式
   export HTTP_PROXY="http://127.0.0.1:7890"
   export HTTPS_PROXY=$HTTP_PROXY
   python openai_server.py
   ```

5. **并发处理**: 当前版本使用单例 AIStudioBot 实例，适合单用户场景。如需支持多用户并发，需要扩展为多实例架构。

## 故障排查

### Bot 初始化失败

检查日志输出，常见问题：
- Chrome 浏览器未安装
- 代理连接失败
- 网络连接问题

### 登录状态丢失

- 检查 Cookie 文件是否正确保存
- 尝试删除 Cookie 文件重新登录
- 检查 `--user-data-dir` 是否有写入权限

### API 返回 503 错误

表示 AIStudioBot 未初始化成功，检查：
- 服务端启动日志
- Bot 状态接口 `/v1/bot/status`

## 许可证

MIT License
