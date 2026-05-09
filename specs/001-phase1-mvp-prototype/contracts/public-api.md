# Public API Contract: MyReactAgent Phase 1

**Feature**: `001-phase1-mvp-prototype`  
**生成时间**: 2026-05-08  
**类型**: Python 库公共接口契约

本文档定义框架面向开发者的公共 API 契约。标注 `STABLE` 的接口在 Phase 1 完成后不得做破坏性变更（可新增，禁止删除或重命名）。标注 `RESERVED` 的接口在当前阶段为占位实现，签名已稳定但行为在后续阶段完善。

---

## 1. 工具定义接口

### 1.1 装饰器方式（FR-008）`STABLE`

```python
from myreactagent.tools import tool

@tool
def calculate(expression: str) -> str:
    """计算数学表达式并返回结果。"""
    return str(eval(expression))

# 等价于创建一个 BaseTool 子类，name="calculate"
```

**契约**:
- 函数名 → `tool.name`（不做任何变换）
- 文档字符串第一行 → `tool.description`（strip 后）
- 函数参数类型注解 → `tool.parameters_schema`（Pydantic JSON Schema）
- 无类型注解的参数默认为 `str`
- 缺少文档字符串时，`description` 为空字符串（不报错）
- 返回值类型注解不影响 Schema 生成（工具返回值通过 `ToolResult` 包装）
- `is_destructive` 默认 `False`，`permission` 默认 `"read"`，可通过参数覆盖：
  ```python
  @tool(is_destructive=True, permission="destructive")
  def delete_file(path: str) -> str:
      """删除指定文件。"""
      ...
  ```

### 1.2 类继承方式（FR-009）`STABLE`

```python
from myreactagent.tools import BaseTool, ToolResult

class WebSearchTool(BaseTool):
    name = "web_search"
    description = "在互联网上搜索信息，返回相关结果摘要。"
    is_destructive = False
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词"},
                "max_results": {"type": "integer", "description": "最大结果数", "default": 5},
            },
            "required": ["query"],
        }

    def execute(self, args: dict) -> ToolResult:
        query = args["query"]
        max_results = args.get("max_results", 5)
        # ... 实际搜索逻辑 ...
        return ToolResult(
            tool_call_id="",   # 框架（ToolRegistry）在 execute() 返回后自动覆盖为正确 ID
            success=True,
            content="搜索结果...",
        )
```

**契约**:
- `name`、`description` 为类属性，MUST 非空字符串
- `parameters_schema` 为属性方法，MUST 返回合法 JSON Schema Object
- `execute(args: dict) → ToolResult`：框架在调用前已完成 Pydantic 验证
- `args` 字典中**不含** `_tool_call_id` 字段；`tool_call_id` 由 `ToolRegistry.execute()` 在调用 `execute()` 之后自动注入到 `ToolResult` 中，工具实现无需也不应从 args 中获取它；在 `execute()` 内将 `tool_call_id` 设为 `""` 或任意占位值均可，框架会覆盖
- 工具抛出的任意异常由框架捕获，转化为 `ToolResult(success=False, error=...)`

---

## 2. Agent 创建与执行接口

### 2.1 创建 Agent `STABLE`

```python
from myreactagent import ReactAgent
from myreactagent.callbacks import ConsoleCallbackHandler

agent = ReactAgent(
    tools=[calculate, WebSearchTool()],   # 混合使用两种工具定义方式
    system_prompt="你是一个助手，使用工具来完成任务。",
    session_id="custom-session-001",      # 可选，不传则自动生成 UUID
    max_iterations=10,                    # 可选，默认 10
    max_messages=20,                      # 可选，默认 20
    keep_last_n=6,                        # 可选，默认 6（轮）
    callbacks=[ConsoleCallbackHandler()], # 可选，默认空列表
    model="gpt-4o-mini",                  # 可选，默认读取 OPENAI_MODEL 环境变量
    base_url="https://...",               # 可选，默认读取 OPENAI_BASE_URL 环境变量
    api_key="sk-...",                     # 可选，默认读取 OPENAI_API_KEY 环境变量
)
```

**契约**:
- `ReactAgent` 实例创建后立即可用，不需要额外初始化步骤
- 每个实例持有独立的 `ConversationMemory` 和 `ToolRegistry`
- `session_id` 在实例生命周期内不变
- `api_key`、`base_url`、`model` 三个参数均支持显式传入，优先级高于对应环境变量（宪法 III：配置 MUST 显式传入）

### 2.2 同步执行（单次问答）`STABLE`

```python
answer: str = agent.run("3 乘以 7 加上 8 等于多少？")
print(answer)  # "3 乘以 7 加上 8 等于 29。"
```

**契约**:
- 返回类型为 `str`（最终答案的完整文本）
- 阻塞直到 ReAct 循环完成（所有工具执行完毕 + LLM 给出最终答案）
- 不抛出因工具执行失败、LLM 重试失败（超出重试次数）之外的异常
- 工具执行失败时返回继续循环，不终止（FR-011）
- 达到 `max_iterations` 时发送追加消息后再调用一次 LLM，返回其输出（宪法 XVII）

### 2.3 同步流式执行（逐词输出）`STABLE`

```python
for token in agent.run_stream("写一首关于秋天的诗。"):
    print(token, end="", flush=True)
print()  # 换行
```

**契约**:
- 返回同步迭代器 `Iterator[str]`，每次 `yield` 一个文本片段
- 文本片段为 LLM 最终答案阶段的 token，工具调用执行阶段不 yield（工具在后台运行）
- 调用方可随时停止迭代（不保证 `on_agent_end` 回调触发）
- 流式模式下 `on_llm_end` 在流结束后触发一次，携带完整拼接内容

### 2.4 多轮对话（复用 Agent 实例）`STABLE`

```python
agent = ReactAgent(tools=[...])
agent.run("我的名字是张三。")
answer = agent.run("我刚才告诉你的名字是什么？")
# answer == "你告诉我的名字是张三。"
```

**契约**:
- 每次 `run()` / `run_stream()` 调用后，对话历史自动更新（用户消息 + Agent 回复）
- 工具调用的消息对也保留在历史中
- `ConversationMemory` 自动管理截断，调用方无需关心

---

## 3. 回调接口

### 3.1 自定义回调处理器 `STABLE`

```python
from myreactagent.callbacks import BaseCallbackHandler
from myreactagent.schemas import CallbackEvent

class MyLogger(BaseCallbackHandler):
    def on_agent_start(self, event: CallbackEvent) -> None:
        print(f"[{event.timestamp}] Agent 启动，会话：{event.session_id}")

    def on_tool_start(self, event: CallbackEvent) -> None:
        print(f"调用工具：{event.data['tool_name']}，参数：{event.data['arguments']}")

    def on_error(self, event: CallbackEvent) -> None:
        print(f"错误：{event.data['error_message']}")

agent = ReactAgent(callbacks=[MyLogger()])
```

**契约**:
- 继承 `BaseCallbackHandler`，仅覆盖关心的方法
- 未覆盖的方法默认为空操作（no-op），不报错
- 回调方法为同步调用（Phase 1），不得在内部使用 `async/await`
- 回调抛出的异常不影响 Agent 主流程（框架内部 try/except 保护）
- 多个 `BaseCallbackHandler` 同时注册时，按传入 `callbacks` 列表的顺序串行调用；单个处理器抛出的异常不影响后续处理器的执行，也不影响 Agent 主流程

### 3.2 内置控制台回调 `STABLE`

```python
from myreactagent.callbacks import ConsoleCallbackHandler

agent = ReactAgent(callbacks=[ConsoleCallbackHandler()])
# 自动打印所有 7 类生命周期事件的格式化信息
```

---

## 4. 事件载荷 Schema `STABLE`

所有回调事件的 `CallbackEvent` 结构（宪法 VII，FR-014）：

```json
{
  "event": "on_tool_start",
  "data": {
    "tool_name": "calculate",
    "tool_call_id": "call_abc123",
    "arguments": {"expression": "3 * 7 + 8"}
  },
  "timestamp": "2026-05-08T10:30:00.000Z",
  "session_id": "550e8400-e29b-41d4-a716-446655440000",
  "run_id": "6ba7b810-9dad-11d1-80b4-00c04fd430c8",
  "span_id": ""
}
```

**契约**:
- 6 个顶层字段（`event`、`data`、`timestamp`、`session_id`、`run_id`、`span_id`）在所有阶段保持不变
- 可新增顶层字段（向后兼容），禁止删除或重命名现有字段（宪法 VII）
- `span_id` 在 Phase 1 始终为空字符串

### `on_agent_start` 载荷结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `user_message` | `str` | 本轮用户输入的原始文本 |
| `system_prompt` | `str \| null` | Agent 实例的系统提示；未设置时为 `null` |

### `on_llm_start` 载荷结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `messages` | `list[dict]` | 发送给 LLM 的完整消息列表（OpenAI 格式） |
| `tools` | `list[dict]` | 发送给 LLM 的工具 schema 列表；工具列表为空时为 `[]` |
| `stream` | `bool` | 是否为流式请求；`run()` 为 `false`，`run_stream()` 为 `true` |

### `on_llm_end` 载荷结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | `str \| null` | LLM 返回的文本内容；工具调用时可能为 `""` 或 `null` |
| `tool_calls` | `list[dict] \| null` | 工具调用请求列表（每项含 `id`、`name`、`arguments`），无工具调用时为 `null` |
| `finish_reason` | `str` | LLM 停止原因，典型值：`"stop"`、`"tool_calls"`、`"length"` |

### `on_tool_start` 载荷结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_name` | `str` | 工具名称 |
| `tool_call_id` | `str` | LLM 分配的工具调用 ID |
| `arguments` | `dict` | 已通过 Pydantic 验证的参数字典（不含 `_tool_call_id`） |

### `on_tool_end` 载荷结构（成功与失败统一格式）

`on_tool_end` 无论工具成功或失败均触发，`data` 字段结构如下：

**成功示例**：
```json
{
  "tool_name": "calculate",
  "tool_call_id": "call_abc123",
  "success": true,
  "result": "29",
  "error_type": null,
  "error_message": null
}
```

**失败示例**（工具执行抛出异常）：
```json
{
  "tool_name": "divide",
  "tool_call_id": "call_xyz789",
  "success": false,
  "result": null,
  "error_type": "ZeroDivisionError",
  "error_message": "除数不能为零"
}
```

**字段说明**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `tool_name` | `str` | 工具名称 |
| `tool_call_id` | `str` | LLM 分配的工具调用 ID |
| `success` | `bool` | 执行是否成功 |
| `result` | `str \| null` | 成功时为工具返回内容（已完成长度截断），失败时为 `null` |
| `error_type` | `str \| null` | 失败时为异常类名（如 `"ZeroDivisionError"`），成功时为 `null` |
| `error_message` | `str \| null` | 失败时为异常消息字符串，成功时为 `null` |

### `on_agent_end` 载荷结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `final_answer` | `str` | Agent 最终输出的完整文本 |
| `iterations` | `int` | 本次 `run()` 实际执行的迭代次数（含安全兜底调用） |

### `on_error` 载荷结构

`on_error` 仅在框架内部错误（非工具执行异常）时触发，目前有三种触发场景：

**场景一：LLM 返回无效 JSON tool_call 参数**

| 字段 | 类型 | 说明 |
|------|------|------|
| `error_type` | `str` | 固定值 `"JSONDecodeError"` |
| `error_message` | `str` | JSON 解析错误的原始消息 |
| `context` | `str` | 描述错误发生位置，格式：`"Failed to parse tool call arguments for '<tool_name>'"` |

**场景二：系统提示超过字符阈值（8000 字符，Phase 1 启发式）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `warning` | `bool` | 固定值 `true`，表示这是 warning 而非致命错误 |
| `error_type` | `str` | 固定值 `"SystemPromptTooLong"` |
| `error_message` | `str` | 描述实际长度与阈值的提示文本 |

**场景三：tool_call 原子对消息数超出 `max_messages` 上限（FR-007b）**

| 字段 | 类型 | 说明 |
|------|------|------|
| `warning` | `bool` | 固定值 `true`，表示这是 warning 而非致命错误 |
| `error_type` | `str` | 固定值 `"ContextOverflow"` |
| `error_message` | `str` | 描述原子对溢出及已完整保留的提示文本 |

**通用约定**：`on_error` 的 `data` 中始终包含 `error_type` 字段；含 `warning: true` 的事件表示 Agent 仍正常运行，调用方可忽略或记录；不含 `warning` 或 `warning: false` 的 `on_error` 表示实际错误，但 Agent 循环仍会尝试继续运行。

---

## 5. 环境变量配置 `STABLE`

| 变量名 | 必填 | 描述 |
|--------|------|------|
| `OPENAI_API_KEY` | 是 | OpenAI 或兼容 API 的密钥 |
| `OPENAI_BASE_URL` | 否 | 自定义 API 地址（如 Azure、本地模型） |
| `OPENAI_MODEL` | 否 | 默认模型，不传时由 SDK 决定 |
| `RUN_INTEGRATION_TESTS` | 否 | 设为 `1` 时启用集成测试（需真实 API Key） |

---

## 6. 错误处理契约 `STABLE`

| 场景 | 行为 |
|------|------|
| 工具执行抛出异常 | 捕获，返回 `ToolResult(success=False, error=str(e))`，Agent 继续循环 |
| 工具参数验证失败 | 返回 `ToolResult(success=False, error=<Pydantic ValidationError>)`，触发 `on_tool_end(success=False)`，不触发 `on_error`（FR-013） |
| LLM 返回无效 JSON tool_call | 触发 `on_error`，将错误作为 tool 结果返回，Agent 继续循环 |
| LLM API 失败（重试后） | SDK `max_retries=3` 内自动重试；超出后抛出 `openai.APIError` 子类 |
| 达到 `max_iterations` | 追加"请给出最终答案"消息，再调用 LLM 一次，返回其输出（不抛出异常） |
| `content` 为 `list[ContentPart]` | 抛出 `NotImplementedError`（Phase 1 多模态预留未实现） |
