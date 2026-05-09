# 数据模型: Phase 1 MVP — ReAct Agent 核心框架

**Feature**: `001-phase1-mvp-prototype`  
**生成时间**: 2026-05-08  
**依赖**: `research.md` 已完成

---

## 实体总览

```
ContentPart (Union)
  ├── TextContentPart
  ├── ImageContentPart        ← Phase 1 预留，触发 NotImplementedError
  └── AudioContentPart        ← Phase 1 预留，触发 NotImplementedError

MessageContent = Union[str, list[ContentPart]]

Message
  ├── role: Literal["system", "user", "assistant", "tool"]
  ├── content: MessageContent
  ├── tool_calls: list[ToolCall] | None    ← assistant 消息携带
  ├── tool_call_id: str | None             ← tool 消息携带
  └── name: str | None                     ← tool 消息携带（工具名）

ToolCall
  ├── id: str
  ├── type: Literal["function"]
  └── function: ToolCallFunction

ToolCallFunction
  ├── name: str
  └── arguments: str    ← JSON 字符串，待解析

ToolResult
  ├── tool_call_id: str
  ├── success: bool
  ├── content: MessageContent   ← 成功时的返回值（Phase 1 仅 str）
  └── error: str | None         ← 失败时的错误信息

CallbackEvent
  ├── event: str                ← 事件类型名称
  ├── data: dict                ← 事件载荷（各事件不同）
  ├── timestamp: str            ← ISO-8601 格式
  ├── session_id: str           ← Agent 实例级别标识
  ├── run_id: str               ← 单次 run() 调用级别标识
  └── span_id: str              ← Phase 1 为空字符串，Phase 4 填充

NextStep (Enum)
  ├── STOP                      ← 终止循环，输出最终答案（Phase 1 完整实现）
  ├── CONTINUE                  ← 执行工具后继续循环（Phase 1 完整实现）
  ├── HANDOFF                   ← 移交控制权至其他 Agent（Phase 2 占位）
  └── INTERRUPT                 ← 等待人工确认（Phase 4 占位）

BaseTool (ABC)
  ├── name: str                 ← 工具名称
  ├── description: str          ← 工具描述（供 LLM 理解）
  ├── is_destructive: bool      ← 是否不可逆操作，默认 False
  ├── permission: Literal[...]  ← "read" | "write" | "destructive"，默认 "read"
  ├── parameters_schema: dict   ← JSON Schema（自动或手动生成）
  └── execute(args: dict) → ToolResult  ← 抽象方法

ToolRegistry
  ├── _tools: dict[str, BaseTool]   ← 内部工具表（实例变量，非类变量）
  ├── register(tool: BaseTool) → None
  ├── get_tool(name: str) → BaseTool | None
  ├── get_openai_schemas() → list[dict]  ← 供 OpenAI API tools 参数
  └── execute(name: str, args: dict) → ToolResult  ← 验证 + 执行入口

ConversationMemory
  ├── _messages: list[Message]   ← 内部消息列表（实例变量）
  ├── max_messages: int          ← 默认 20
  ├── keep_last_n: int           ← 保护最近 N 轮，默认 6
  ├── add(message: Message) → None    ← 添加消息后触发截断检查
  ├── get_messages() → list[Message]  ← 返回当前消息列表（已截断）
  └── _truncate() → None              ← 内部截断逻辑

LLMClient
  ├── model: str                        ← 默认从 OPENAI_MODEL 环境变量读取
  ├── _client: openai.OpenAI            ← 内部 SDK 实例（max_retries=3）
  ├── chat(messages, tools) → ChatCompletion          ← 仅非流式，ReactAgent.run() 使用
  └── chat_stream(messages, tools) → Iterator[ChatCompletionChunk]

BaseCallbackHandler (ABC)
  ├── on_agent_start(event: CallbackEvent) → None
  ├── on_llm_start(event: CallbackEvent) → None
  ├── on_llm_end(event: CallbackEvent) → None
  ├── on_tool_start(event: CallbackEvent) → None
  ├── on_tool_end(event: CallbackEvent) → None
  ├── on_agent_end(event: CallbackEvent) → None
  └── on_error(event: CallbackEvent) → None
  （所有方法默认空实现，子类按需覆盖）

ConsoleCallbackHandler(BaseCallbackHandler)
  └── 覆盖所有 7 个方法，打印格式化的事件信息到 stdout

ReactAgent
  ├── session_id: str                     ← 会话标识，构造时自动生成或由调用方传入
  ├── system_prompt: str | None           ← 系统提示
  ├── max_iterations: int                 ← 默认 10
  ├── _memory: ConversationMemory         ← 实例私有
  ├── _tools: ToolRegistry                ← 实例私有
  ├── _llm: LLMClient                     ← 实例私有
  ├── _callbacks: list[BaseCallbackHandler]  ← 实例私有
  ├── _emit(event: CallbackEvent) → None  ← 内部分发回调
  ├── run(user_message: str) → str                    ← 同步执行，返回最终答案
  └── run_stream(user_message: str) → Iterator[str]  ← 同步流式，逐词 yield
```

---

## 详细模型定义

### ContentPart — 多模态内容块（Phase 1 预留接口）

```python
class TextContentPart(BaseModel):
    type: Literal["text"] = "text"
    text: str

class ImageContentPart(BaseModel):
    type: Literal["image_url"] = "image_url"
    image_url: dict  # {"url": str, "detail": str}

class AudioContentPart(BaseModel):
    type: Literal["input_audio"] = "input_audio"
    input_audio: dict  # {"data": str, "format": str}

ContentPart = Union[TextContentPart, ImageContentPart, AudioContentPart]
MessageContent = Union[str, list[ContentPart]]
```

**Phase 1 约束**：`LLMClient` 在收到 `list[ContentPart]` 时 MUST 抛出 `NotImplementedError`。Phase 4 移除该限制并添加序列化逻辑。

---

### Message — 对话消息

```python
class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: MessageContent
    tool_calls: list[ToolCall] | None = None       # role=assistant 时使用
    tool_call_id: str | None = None                 # role=tool 时使用
    name: str | None = None                         # role=tool 时使用（工具名）

    def to_openai_dict(self) -> dict:
        # 转换为 OpenAI API 兼容的消息格式
        ...
```

**字段约束**:
- `role="tool"` 时，`tool_call_id` MUST 非空
- `role="assistant"` 且 `tool_calls` 非空时，`content` 可以为空字符串（OpenAI 协议要求）
- `content` 为 `list[ContentPart]` 时，Phase 1 在序列化阶段抛出 `NotImplementedError`

---

### ToolCall / ToolCallFunction — 工具调用请求

```python
class ToolCallFunction(BaseModel):
    name: str
    arguments: str  # JSON 字符串，由 LLM 生成

class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction
```

---

### ToolResult — 工具执行结果

```python
class ToolResult(BaseModel):
    tool_call_id: str
    success: bool
    content: MessageContent = ""  # 成功时非空，Phase 1 仅使用 str 分支
    error: str | None = None      # 失败时的错误描述

    def to_message(self) -> Message:
        # 转换为 role="tool" 的 Message，加入对话历史
        content_str = self.content if isinstance(self.content, str) else self.error or "error"
        return Message(role="tool", tool_call_id=self.tool_call_id, content=content_str)
```

---

### CallbackEvent — 生命周期事件载荷

```python
class CallbackEvent(BaseModel):
    event: str          # 事件类型，如 "on_agent_start"
    data: dict          # 事件特定数据
    timestamp: str      # ISO-8601，如 "2026-05-08T10:00:00.000Z"
    session_id: str     # Agent 实例标识
    run_id: str         # 单次 run() 标识
    span_id: str = ""   # Phase 1 留空，Phase 4 填充 OTel span id
```

**各事件 `data` 字段内容**:

| event | data 字段 |
|-------|-----------|
| `on_agent_start` | `{"user_message": str, "system_prompt": str \| None}` |
| `on_llm_start` | `{"messages": list[dict], "tools": list[dict], "stream": bool}` |
| `on_llm_end` | `{"content": str \| None, "tool_calls": list[dict] \| None, "finish_reason": str}` |
| `on_tool_start` | `{"tool_name": str, "tool_call_id": str, "arguments": dict}` |
| `on_tool_end` | `{"tool_name": str, "tool_call_id": str, "success": bool, "result": str}` |
| `on_agent_end` | `{"final_answer": str, "iterations": int}` |
| `on_error` | `{"error_type": str, "error_message": str, "context": str}` |

---

### NextStep — ReAct 循环走向枚举

```python
class NextStep(Enum):
    STOP = "stop"           # 终止，输出最终答案（Phase 1 完整实现）
    CONTINUE = "continue"   # 执行工具后继续（Phase 1 完整实现）
    HANDOFF = "handoff"     # 移交其他 Agent（Phase 2 占位，抛 NotImplementedError）
    INTERRUPT = "interrupt"  # 等待人工确认（Phase 4 占位，抛 NotImplementedError）
```

---

### BaseTool — 工具抽象基类

```python
class BaseTool(ABC):
    name: str                           # 工具唯一名称
    description: str                    # 供 LLM 理解的自然语言描述
    is_destructive: bool = False        # 是否不可逆（Phase 4 HITL 使用）
    permission: Literal["read", "write", "destructive"] = "read"  # 权限级别

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        # 返回 JSON Schema（"type": "object", "properties": {...}）
        ...

    @abstractmethod
    def execute(self, args: dict) -> ToolResult:
        ...
```

**装饰器定义示例（FR-008）**:
```python
@tool
def add_numbers(a: int, b: int) -> int:
    """将两个整数相加并返回结果。"""
    return a + b
# 自动生成：name="add_numbers", description="将两个整数相加并返回结果。"
# parameters_schema 由 Pydantic 从函数签名自动生成
```

**类继承定义示例（FR-009）**:
```python
class SearchTool(BaseTool):
    name = "search"
    description = "在网络上搜索信息。"
    is_destructive = False
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def execute(self, args: dict) -> ToolResult:
        ...
```

---

### ConversationMemory — 对话历史管理

```python
class ConversationMemory:
    def __init__(
        self,
        max_messages: int = 20,
        keep_last_n: int = 6,       # 保护最近 N 轮（每轮 ≈ user + assistant）
    ): ...
```

**截断保护规则（FR-006）**:
1. `role="system"` 消息永远保留，不计入 `max_messages`
2. `tool_call_pairs`：`role=assistant`（含 `tool_calls`）+ 紧随其后所有 `role=tool` 消息，原子保护
3. `last_n_rounds`：从末尾向前数 `keep_last_n` 轮完整对话（user + assistant），保护不截断
4. 仅保护区外的中间普通消息（user/assistant 无工具调用）可被截断

---

### ReactAgent — 主 Agent 类

```python
class ReactAgent:
    def __init__(
        self,
        tools: list[BaseTool] | None = None,
        system_prompt: str | None = None,
        session_id: str | None = None,         # 不传则自动生成 UUID
        max_iterations: int = 10,
        max_messages: int = 20,
        keep_last_n: int = 6,
        callbacks: list[BaseCallbackHandler] | None = None,
        model: str | None = None,              # 不传则读取 OPENAI_MODEL 环境变量
        base_url: str | None = None,           # 不传则读取 OPENAI_BASE_URL 环境变量
    ): ...

    def run(self, user_message: str) -> str:
        """同步执行完整的 ReAct 循环，返回最终答案字符串。"""
        ...

    def run_stream(self, user_message: str) -> Iterator[str]:
        """同步流式执行，逐 token yield 最终答案文本片段。"""
        ...
```

---

## 状态转换图

```
用户消息输入
     │
     ▼
[on_agent_start]
     │
     ▼
┌─────────────────────────────────────────────┐
│               ReAct 循环                     │
│                                              │
│  [on_llm_start] → LLM 请求 → [on_llm_end]  │
│          │                                   │
│          ├─ finish_reason="stop" ──────────► NextStep.STOP
│          │                                   │
│          └─ finish_reason="tool_calls" ───► NextStep.CONTINUE
│                    │                         │
│                    ▼                         │
│            for each tool_call:               │
│              [on_tool_start]                 │
│              执行工具                         │
│              [on_tool_end]                   │
│              添加 tool 结果到历史             │
│                    │                         │
│                    └─────────────────────────┘
│                                              │
│  ── 达到 max_iterations ──────────────────► 发送"请给出最终答案"追加消息
│                                              │
│              最后一次 LLM 调用               │
└─────────────────────────────────────────────┘
     │
     ▼
[on_agent_end]
     │
     ▼
返回最终答案
```

---

## 层次依赖关系

```
myreactagent/
├── schemas/          ← 纯数据类型，无业务逻辑，可被任意层导入
│   ├── messages.py   (Message, ContentPart, ToolCall, ToolCallFunction, MessageContent)
│   ├── events.py     (CallbackEvent, NextStep)
│   └── tools.py      (ToolResult)
│
├── tools/            ← 工具系统层，仅依赖 schemas/
│   ├── base.py       (BaseTool ABC)
│   ├── decorator.py  (@tool 装饰器)
│   └── registry.py   (ToolRegistry)
│
├── llm/              ← LLM 交互层，仅依赖 schemas/
│   └── client.py     (LLMClient)
│
├── memory/           ← 记忆层，仅依赖 schemas/
│   └── conversation.py (ConversationMemory)
│
├── callbacks/        ← 回调层，依赖 schemas/
│   ├── base.py       (BaseCallbackHandler ABC)
│   └── console.py    (ConsoleCallbackHandler)
│
└── agent/            ← Agent 层，依赖所有下层
    └── react.py      (ReactAgent)
```

**禁止的依赖方向（宪法 IV）**:
- `tools/` 禁止导入 `agent/` 或 `llm/`
- `memory/` 禁止导入 `agent/`
- `llm/` 禁止导入 `agent/`、`memory/`、`tools/`
