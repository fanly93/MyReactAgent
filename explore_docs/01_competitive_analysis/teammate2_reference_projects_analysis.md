# 开源 Agent 框架深度源码调研报告

> 调研对象：adk-python、deepagents、hermes-agent、langchain、openai-agents-python
> 调研时间：2026-05-08
> 调研目的：为 MyReactAgent 提供可借鉴的实现参考

---

## 1. 核心循环实现

### 1.1 openai-agents-python

**核心文件：**
- `src/agents/run.py`（Runner / AgentRunner 入口）
- `src/agents/run_internal/run_loop.py`（`run_single_turn`、`get_new_response`、`run_single_turn_streamed`）
- `src/agents/run_internal/run_steps.py`（`NextStep*` 步骤类型）

**循环结构：**

`AgentRunner.run()` 在 `run.py` 第 757 行维护一个 `while True` 大循环，每次迭代调用 `run_single_turn()`，通过返回的 `SingleStepResult.next_step` 决定循环走向。

```python
# src/agents/run_internal/run_steps.py
class NextStepHandoff:    ...   # 切换子 Agent
class NextStepFinalOutput: ...  # 终止并输出
class NextStepRunAgain:    ...  # 继续循环（有工具调用）
class NextStepInterruption: ... # Human-in-the-loop 中断
```

`run.py` 第 1046-1047 行的 max_turns 检查：

```python
current_turn += 1
if max_turns is not None and current_turn > max_turns:
    max_turns_error = MaxTurnsExceeded(f"Max turns ({max_turns}) exceeded")
```

**同步 vs 异步：** 同步接口 `Runner.run_sync()` 通过 `asyncio.run()` 包装异步主逻辑。完整逻辑均为 `async def`，同步版本是薄壳。

### 1.2 adk-python（Google ADK）

**核心文件：**
- `src/google/adk/runners.py`（Runner，入口 `run_async()`）
- `src/google/adk/flows/llm_flows/base_llm_flow.py`（BaseLlmFlow，核心循环）
- `src/google/adk/flows/llm_flows/single_flow.py`（SingleFlow）
- `src/google/adk/flows/llm_flows/auto_flow.py`（AutoFlow，带 agent_transfer）

**循环结构：**

ADK 采用 **事件流（AsyncGenerator[Event, None]）** 模型，不是 while 循环。

`BaseLlmFlow._postprocess_async()` 方法（第 935 行）检查 `get_function_calls()` 判断是否需要工具调用：

```python
# base_llm_flow.py 第 977-991 行
if model_response_event.get_function_calls():
    if model_response_event.partial:
        return
    async with Aclosing(
        self._postprocess_handle_function_calls_async(...)
    ) as agen:
        async for event in agen:
            yield event
```

`Runner.run_async()` 通过 `async for event in agent.run_async(...)` 消费事件流，没有显式的 while 循环，而是通过协程链式传递。

**`finish_reason` 等价逻辑：** 通过 `llm_response.content`、`llm_response.error_code`、`get_function_calls()` 等字段判断是否结束，不依赖 OpenAI 的 `finish_reason` 字段（因为 ADK 底层是 Google GenAI SDK）。

### 1.3 hermes-agent

**核心文件：**
- `run_agent.py`（AIAgent 类，`run_conversation()` 方法，第 10768 行）

**循环结构：**

经典 while 循环，第 11152 行：

```python
while (api_call_count < self.max_iterations and self.iteration_budget.remaining > 0) or self._budget_grace_call:
    api_call_count += 1
    # ... API 调用
    # ... 检查 finish_reason
    # ... 处理 tool_calls
```

检查 `finish_reason` 使用 `_should_treat_stop_as_truncated()` 方法（第 3236 行），含特殊处理：对 Ollama/GLM 等模型的异常 `stop` 做降级兼容。此外还有 `_looks_like_codex_intermediate_ack()` 检测 ACK 消息，防止过早退出。

**同步实现：** hermes-agent 主循环是同步的，工具执行通过 `asyncio.run_coroutine_threadsafe()` 或 `_TOOL_THREAD_POOLS` 线程池将异步工具转为同步调用。

### 1.4 langchain

**核心文件：**
- `libs/core/langchain_core/agents.py`（`AgentAction`、`AgentFinish` 数据结构）
- `libs/core/langchain_core/language_models/chat_models.py`（`BaseChatModel`，invoke/stream/ainvoke 接口）

LangChain-core 只定义了数据结构和接口，具体的 Agent 循环在上层 `langchain` 包（`libs/langchain/langchain_v1/agents/`）实现。LangChain 的循环依赖 LCEL（LangChain Expression Language）管道，通过 `AgentFinish` 标志终止。

`AgentFinish`（第 146-168 行）：

```python
class AgentFinish(Serializable):
    return_values: dict   # 返回值
    log: str              # 完整 LLM 输出
    type: Literal["AgentFinish"] = "AgentFinish"
```

**同步/异步：** `BaseChatModel` 同时提供 `invoke`/`ainvoke`/`stream`/`astream`，所有同步方法默认在线程池执行对应异步方法（`run_in_executor`）。

### 1.5 deepagents

**核心文件：**
- `libs/deepagents/deepagents/graph.py`（`create_deep_agent()`）
- 依赖 `langchain.agents.create_agent` + LangGraph 状态图

deepagents 是 LangGraph 的高阶封装，循环由 LangGraph 的 `CompiledStateGraph` 驱动，不直接实现 while 循环，而是通过图节点（node）和边（edge）定义有限状态机。

### 横向对比表

| 项目 | 循环机制 | `finish_reason` 判断方式 | 同步接口实现 |
|------|----------|--------------------------|--------------|
| openai-agents | `while True` + `NextStep` 枚举 | OpenAI `finish_reason=="stop"` vs tool_calls | `asyncio.run()` 包装 |
| adk-python | `AsyncGenerator[Event]` 链式 | `get_function_calls()` 为空时终止 | 同步 `run()` 在 thread 中运行事件循环 |
| hermes-agent | `while api_call_count < max_iterations` | `finish_reason` + 多种特殊 case 兼容 | 原生同步，工具执行走线程池 |
| langchain | LCEL 管道 + `AgentFinish` | 返回 `AgentFinish` 实例时终止 | `invoke`/`ainvoke` 均支持 |
| deepagents | LangGraph 状态图边 | 图终止节点 | LangGraph 提供 |

---

## 2. 工具系统实现

### 2.1 openai-agents-python

**核心文件：**
- `src/agents/tool.py`（`FunctionTool` dataclass，`function_tool` 装饰器）
- `src/agents/function_schema.py`（`function_schema()`，Schema 自动生成）

**FunctionTool 数据结构（tool.py 第 282 行）：**

```python
@dataclass
class FunctionTool:
    name: str
    description: str
    params_json_schema: dict[str, Any]
    on_invoke_tool: Callable[[ToolContext[Any], str], Awaitable[Any]]
    strict_json_schema: bool = True
    is_enabled: bool | Callable[...] = True
    needs_approval: bool | Callable[...] = False
    timeout_seconds: float | None = None
    # ...
```

**Schema 自动生成（function_schema.py 第 224 行）：**

`function_schema()` 函数通过以下步骤生成 JSON Schema：
1. 调用 `generate_func_documentation()` 解析 docstring（支持 google/numpy/sphinx 三种格式，通过 `griffe` 库）
2. 通过 `inspect.signature()` + `get_type_hints()` 获取参数信息
3. 使用 `pydantic.create_model()` 动态创建参数 Pydantic 模型
4. 调用 `dynamic_model.model_json_schema()` 生成 JSON Schema
5. 调用 `ensure_strict_json_schema()` 转为 OpenAI 严格模式

```python
# function_schema.py 第 406-424 行
dynamic_model = create_model(f"{func_name}_args", __base__=BaseModel, **fields)
json_schema = dynamic_model.model_json_schema()
if strict_json_schema:
    json_schema = ensure_strict_json_schema(json_schema)
return FuncSchema(
    name=func_name,
    description=description_override or doc_info.description,
    params_pydantic_model=dynamic_model,
    params_json_schema=json_schema,
    ...
)
```

**工具执行结果：** 工具通过 `on_invoke_tool(ctx, json_str)` 返回任意值，框架封装为 `FunctionToolResult`（第 261 行，含 `tool`、`output`、`run_item`、`interruptions` 字段）。

**工具注册：** 无显式 Registry 类，工具直接以列表形式传入 `Agent(tools=[...])`，运行时通过 `get_all_tools()` 收集并构建 lookup map（`build_function_tool_lookup_map()`）。

### 2.2 adk-python

**核心文件：**
- `src/google/adk/tools/base_tool.py`（`BaseTool` ABC）
- `src/google/adk/tools/function_tool.py`（`FunctionTool`）
- `src/google/adk/tools/agent_tool.py`（`AgentTool`）

**BaseTool 接口：**

```python
class BaseTool(BaseModel, ABC):
    name: str
    description: str
    # 异步执行接口
    async def run_async(self, *, args: dict[str, Any], tool_context: ToolContext) -> Any: ...
    # 声明 Function schema
    def _get_declaration(self) -> types.FunctionDeclaration: ...
```

ADK 使用 Google GenAI SDK 的 `types.FunctionDeclaration` 类型，不是 OpenAI JSON Schema 格式。

**工具注册：** 工具以列表形式传入 `LlmAgent(tools=[...])`, 在 `base_llm_flow.py` 中通过 `_process_agent_tools()` 统一处理注册。

### 2.3 hermes-agent

**核心文件：**
- `tools/registry.py`（`ToolRegistry` 单例、`ToolEntry` 数据结构）

**ToolRegistry 数据结构（registry.py 第 143 行）：**

```python
class ToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolEntry] = {}
        self._toolset_checks: Dict[str, Callable] = {}
        self._toolset_aliases: Dict[str, str] = {}
        self._lock = threading.RLock()      # 线程安全读写
        self._generation: int = 0           # 生成计数器（用于缓存失效）
```

**ToolEntry（registry.py 第 77 行）：**

```python
class ToolEntry:
    __slots__ = ("name", "toolset", "schema", "handler", "check_fn",
                 "requires_env", "is_async", "description", "emoji",
                 "max_result_size_chars")
```

工具在模块导入时通过 `registry.register(name, toolset, schema, handler, ...)` 自注册，`discover_builtin_tools()` 使用 AST 扫描工具目录找到含 `registry.register()` 调用的文件再 import。

**Schema 生成：** 工具 schema 直接以 `dict` 形式手动编写（OpenAI Function Calling 格式），不自动从函数签名生成。

### 2.4 langchain

**核心文件：**
- `libs/core/langchain_core/tools/base.py`（`BaseTool` ABC）
- `libs/core/langchain_core/tools/convert.py`（`@tool` 装饰器）
- `libs/core/langchain_core/tools/structured.py`（`StructuredTool`）

**`@tool` 装饰器（convert.py）：**

`tool()` 通过 `StructuredTool.from_function()` 创建工具，内部通过 `pydantic.validate_arguments` + `inspect.signature` 自动生成 `args_schema`（Pydantic BaseModel），再通过 `args_schema.schema()` 导出 JSON Schema。支持 `parse_docstring=True` 解析 Google 格式 docstring。

**ToolResult 等价：** LangChain 工具直接返回 `str | Any`，框架负责将结果转为 `ToolMessage` 对象加入消息历史。

### 2.5 deepagents

deepagents 工具系统基于 LangChain 的 `BaseTool`，通过 LangGraph `AgentState` 管理工具调用和结果，无独立工具注册机制。

### 横向对比表

| 项目 | Registry 数据结构 | Schema 自动生成 | ToolResult 封装 |
|------|-------------------|-----------------|-----------------|
| openai-agents | Agent.tools 列表 + 运行时 lookup map | `function_schema()` → griffe + pydantic create_model | `FunctionToolResult` dataclass |
| adk-python | Agent.tools 列表 + toolset 抽象 | `_get_declaration()` → GenAI FunctionDeclaration | 工具直接返回 Any，框架包装为 FunctionResponse |
| hermes-agent | `ToolRegistry` 单例（线程安全字典） | 手动编写 dict schema | 工具返回 str，框架处理大小限制 |
| langchain | 无全局 Registry，工具列表传入 | `StructuredTool.from_function()` + pydantic | 直接返回值，框架包装为 ToolMessage |
| deepagents | 继承 LangChain BaseTool | 同 LangChain | 同 LangChain |

---

## 3. 消息与上下文管理

### 3.1 openai-agents-python

**核心文件：**
- `src/agents/items.py`（`RunItem`、`ModelResponse`、`TResponseInputItem` 等）
- `src/agents/run_internal/items.py`（`run_items_to_input_items()`、`prepare_model_input_items()`）

消息格式直接使用 OpenAI Responses API 的类型（`TResponseInputItem`），与 OpenAI SDK 深度耦合。

`run_items_to_input_items()` 将已处理的运行项（`RunItem`）转换回 API 输入格式，实现消息历史与 API 调用格式的互转。

**Token 计数/窗口截断：** 框架本身没有内置 token 计数，但 `RunConfig.max_turns` 限制循环轮次。Token 窗口管理交由 OpenAI 服务端处理（通过 `conversation_id` 或 `previous_response_id` 实现服务端状态）。

**多轮历史：** `generated_items: list[RunItem]` 在循环中累积，每次 `run_single_turn()` 接收完整历史。

### 3.2 adk-python

**核心文件：**
- `src/google/adk/events/event.py`（`Event` —— 统一消息结构）
- `src/google/adk/sessions/session.py`（`Session` 存储对话历史）
- `src/google/adk/flows/llm_flows/contents.py`（将 Session Events 转为 LLM Content）

ADK 的核心消息抽象是 `Event`（含 `content`、`invocation_id`、`author`、`actions`、`partial` 等字段），比 OpenAI 消息结构更丰富。

`contents.py` 中的 `request_processor` 负责从 Session 历史中提取 LLM 可理解的 `LlmRequest.contents`，实现事件历史 → LLM 输入的转换。

**Token 窗口：** ADK 提供 `compaction.py`（`sliding_window` 策略），在 `runners.py` 中触发 `_run_compaction_for_sliding_window()`，对超出窗口的旧消息进行摘要压缩。

### 3.3 hermes-agent

**消息结构：** 标准 OpenAI Chat Completions 格式（`{"role": ..., "content": ..., "tool_calls": [...]}` 字典）。

**Token 计数（`agent/model_metadata.py`）：**

```python
def estimate_messages_tokens_rough(messages, ...) -> int:
    # 粗粒度估算：字符数 // 4
    sum(len(str(v)) for v in messages) // 4
```

hermes-agent 在 `run_conversation()` 第 11005-11063 行实现 **预飞行压缩（preflight compression）**：在进入主循环前检查 token 是否超阈值，超出则触发 `_compress_context()` 进行最多 3 轮压缩。

**Context Compressor（`agent/context_compressor.py`）：** 使用 LLM 对中间历史进行摘要，保护首尾 N 条消息。

### 3.4 langchain

**核心文件：**
- `libs/core/langchain_core/chat_history.py`（`BaseChatMessageHistory` ABC）
- `libs/core/langchain_core/messages/`（`AIMessage`、`HumanMessage`、`ToolMessage` 等）

`BaseChatMessageHistory` 定义了 `add_messages()` / `messages` 接口，子类实现持久化（Redis、SQLite 等）。Token 截断通过 `ConversationTokenBufferMemory` 等 Memory 类实现，使用 `tiktoken` 计数。

### 3.5 deepagents

deepagents 基于 LangGraph `AgentState`，消息存在 `state["messages"]` 列表中，通过 `MemoryMiddleware` 扩展长期记忆。

### 横向对比表

| 项目 | 消息格式 | Token 计数 | 窗口截断策略 |
|------|----------|------------|--------------|
| openai-agents | OpenAI TResponseInputItem | 无（服务端管理） | max_turns 限制，session conversation_id |
| adk-python | Event（GenAI Content） | 无内置计数 | sliding_window compaction |
| hermes-agent | OpenAI Chat dict | 字符数 // 4 粗估 | 预飞行压缩 + LLM 摘要（最多 3 轮） |
| langchain | BaseMessage 子类 | tiktoken | ConversationTokenBufferMemory |
| deepagents | LangGraph AgentState messages | 同 LangChain | MemoryMiddleware |

---

## 4. 多 Agent 编排实现

### 4.1 openai-agents-python

**核心文件：**
- `src/agents/agent.py`（`Agent` 类，`as_tool()` 方法）
- `src/agents/tool.py`（`FunctionTool`，`_is_agent_tool` 内部标记）

**子 Agent 包装为 Tool：**

`Agent.as_tool()` 方法将子 Agent 包装为 `FunctionTool`，内部通过 `_is_agent_tool=True` 标记，在 `on_invoke_tool` 中启动嵌套的 `Runner.run()`：

```python
# agent.py 中 as_tool() 的核心逻辑（简化）
async def _invoke_agent_as_tool(ctx, input_str):
    result = await Runner.run(agent, input_str, context=ctx)
    return result.final_output
```

`FunctionTool` 通过 `ToolOrigin(type=ToolOriginType.AGENT_AS_TOOL)` 记录来源（`tool.py` 第 176 行）。

**Orchestrator 模式：** 无独立 OrchestratorAgent 类，主 Agent 的 `tools` 列表包含子 Agent 转换的 FunctionTool，复用相同的 ReAct 循环。

**Handoff（切换 Agent）：** `NextStepHandoff` 机制（`run_steps.py` 第 144 行）可在不嵌套的情况下将控制权交给另一个 Agent，适合顺序编排。

### 4.2 adk-python

**核心文件：**
- `src/google/adk/tools/agent_tool.py`（`AgentTool`）

**AgentTool 实现（agent_tool.py 第 94-286 行）：**

```python
class AgentTool(BaseTool):
    agent: BaseAgent

    async def run_async(self, *, args, tool_context):
        # 创建独立的子 Runner
        runner = Runner(
            app_name=child_app_name,
            agent=self.agent,
            session_service=InMemorySessionService(),
            ...
        )
        # 异步迭代子 Agent 的事件流
        async for event in runner.run_async(...):
            if event.actions.state_delta:
                tool_context.state.update(event.actions.state_delta)
            if event.content:
                last_content = event.content
        # 返回最后一条内容作为工具结果
        return merged_text
```

每次 AgentTool 调用都会创建独立的 `Runner` 实例（含独立的 `InMemorySessionService`），状态通过 `tool_context.state` 在父子间同步。

**并行 Agent（ParallelAgent）：** `src/google/adk/agents/parallel_agent.py` 支持多 Agent 并行执行。

### 4.3 hermes-agent

hermes-agent 使用 `delegate_task` 工具启动子 Agent（`tools/mixture_of_agents_tool.py`），子 Agent 以独立的 `AIAgent` 实例在 `ThreadPoolExecutor` 中并发运行。父 Agent 通过工具返回值获取子 Agent 输出，没有显式的 AgentTool 抽象。

### 4.4 langchain

**核心文件：**
- `libs/core/langchain_core/tools/base.py`（`BaseTool`）

LangChain 中子 Agent 通过 `StructuredTool.from_function(agent.invoke)` 手动包装为工具，无内置的 AgentTool 类（Agent-as-Tool 是社区模式，非框架内置）。

### 4.5 deepagents

**核心文件：**
- `libs/deepagents/deepagents/middleware/subagents.py`（`SubAgentMiddleware`、`SubAgent`）

deepagents 通过 `SubAgentMiddleware` 将 `task` 工具映射到 `SubAgent.run()`，通过 `AsyncSubAgentMiddleware` 支持异步并行子 Agent。

### 横向对比表

| 项目 | Agent-as-Tool 实现 | 父子状态共享 | 并行编排 |
|------|-------------------|--------------|----------|
| openai-agents | `Agent.as_tool()` → FunctionTool | 通过 RunContext 传递 | asyncio.gather（多工具并发） |
| adk-python | `AgentTool(agent=...)` | `tool_context.state` 双向同步 | `ParallelAgent` 原生支持 |
| hermes-agent | `delegate_task` 工具 + ThreadPoolExecutor | 无（结果通过工具返回值传递） | 多线程并发 |
| langchain | 手动包装 `StructuredTool.from_function(agent.invoke)` | 无内置机制 | 无内置，需 LangGraph |
| deepagents | `SubAgentMiddleware` + `task` 工具 | LangGraph State | `AsyncSubAgentMiddleware` |

---

## 5. 流式处理实现

### 5.1 openai-agents-python

**核心文件：**
- `src/agents/run_internal/run_loop.py`（`run_single_turn_streamed()`，第 1242 行）
- `src/agents/run_internal/streaming.py`（`stream_step_items_to_queue()`）
- `src/agents/stream_events.py`（流式事件类型）

**tool_call delta 碎片组装：**

openai-agents 直接使用 OpenAI Responses API 的流式事件（`ResponseOutputItemDoneEvent`、`ResponseFunctionToolCall` 等），Responses API 在服务端已完成工具调用碎片的组装，客户端只需在 `ResponseOutputItemDoneEvent` 时处理完整的工具调用。

对于 Chat Completions API，通过 `run_single_turn_streamed()` 处理流式事件：

```python
# run_loop.py，run_single_turn_streamed 内部（第 1242 行）
async for event in stream:
    # RawResponsesStreamEvent 对应原始 SSE 事件
    queue.put_nowait(RawResponsesStreamEvent(data=event))
    # 当工具调用完成时（ResponseOutputItemDoneEvent）
    if isinstance(event, ResponseOutputItemDoneEvent):
        # 处理完整的 tool_call item
```

**流式与非流式统一：** 通过 `asyncio.Queue[StreamEvent]` 将流式事件统一封装，消费者（如 `RunResultStreaming.stream_events()`）通过异步迭代队列获取事件，对外暴露统一的事件流接口。

### 5.2 adk-python

ADK 的核心架构本身就是 `AsyncGenerator[Event]`，天然支持流式：

```python
# base_llm_flow.py
async def _run_one_step_async(...) -> AsyncGenerator[Event, None]:
    async for llm_response in self._call_llm_async(...):
        async for event in self._postprocess_async(...):
            model_response_event.id = Event.new_id()
            yield event  # 立即推送每个事件
```

**tool_call 碎片：** ADK 通过 `model_response_event.partial` 标志区分碎片（partial=True 时跳过工具执行），只在完整事件（partial=False）时处理 function_calls。

### 5.3 hermes-agent

**核心文件：**
- `run_agent.py`（`_interruptible_api_call()`，含 streaming 路径）
- `agent/think_scrubber.py`（`StreamingThinkScrubber` — 过滤 think 标签）
- `agent/memory_manager.py`（`StreamingContextScrubber` — 过滤记忆注入块）

hermes-agent 在有 `stream_callback` 时使用 OpenAI streaming API，通过 `StreamingThinkScrubber` 过滤 `<think>...</think>` 块后将 delta 推给 stream_callback：

```python
# run_agent.py（简化）
for chunk in client.chat.completions.create(..., stream=True):
    delta = chunk.choices[0].delta
    if delta.content:
        visible = think_scrubber.feed(delta.content)
        if stream_callback and visible:
            stream_callback(visible)
    if chunk.choices[0].finish_reason:
        # 流式完成
```

**tool_call delta 组装：** hermes-agent 自实现了 `_assemble_streaming_tool_calls()` 方法，将多个 `delta.tool_calls` 碎片按 `index` 拼接 `function.name` 和 `function.arguments` 字符串。

### 5.4 langchain

**核心文件：**
- `libs/core/langchain_core/language_models/chat_models.py`（`BaseChatModel.astream()`）

LangChain 通过 `AIMessageChunk` 积累 token：

```python
# chat_models.py 中的 astream 模式
async def astream(self, input, ...):
    async for chunk in self._astream(...):
        yield chunk  # 每个 chunk 是 AIMessageChunk

# 消费者通过 += 合并
full_response = None
async for chunk in model.astream(messages):
    if full_response is None:
        full_response = chunk
    else:
        full_response += chunk  # AIMessageChunk.__add__ 实现合并
```

`message_chunk_to_message()` 将完整的 `AIMessageChunk` 转为 `AIMessage`。

**tool_call delta 组装：** 通过 `AIMessageChunk.tool_call_chunks` 列表，每个 chunk 含 `index`/`name`/`args` 字段，`__add__` 方法负责合并相同 index 的 chunk。

### 横向对比表

| 项目 | tool_call delta 组装 | 流式/非流式统一接口 | 特殊处理 |
|------|---------------------|---------------------|---------|
| openai-agents | 服务端（Responses API）已组装 | asyncio.Queue + StreamEvent | 支持 Chat Completions 和 Responses API 两种后端 |
| adk-python | partial 标志控制，完整事件才执行工具 | 统一 AsyncGenerator[Event] | 实时 Live API 支持 |
| hermes-agent | 手动按 index 拼接 name+arguments | stream_callback 回调 | think 标签过滤、记忆块过滤 |
| langchain | `AIMessageChunk.__add__()` | invoke/astream/stream 对称接口 | `tool_call_chunks` 按 index 合并 |
| deepagents | 继承 LangChain | 继承 LangChain | — |

---

## 6. 记忆系统实现

### 6.1 openai-agents-python

**核心文件：**
- `src/agents/memory/`（`Session` 类，会话持久化）

openai-agents 的"记忆"主要是会话历史持久化（`Session`），通过 `save_result_to_session()` 存储 items，下次运行通过 `prepare_input_with_session()` 加载。没有内置的向量检索 / RAG 能力，更多是短期会话记忆。

### 6.2 adk-python

**核心文件：**
- `src/google/adk/memory/base_memory_service.py`（`BaseMemoryService` ABC）
- `src/google/adk/memory/vertex_ai_rag_memory_service.py`（Vertex AI RAG 实现）
- `src/google/adk/memory/in_memory_memory_service.py`（内存实现）

ADK 的记忆 ABC 接口（`base_memory_service.py` 第 44 行）：

```python
class BaseMemoryService(ABC):
    async def add_session_to_memory(self, session: Session) -> None: ...
    async def search_memory(self, *, app_name, user_id, query) -> SearchMemoryResponse: ...
```

`InMemoryMemoryService` 用于测试，`VertexAiRagMemoryService` 接入 Vertex AI RAG。Runner 在每次会话结束后调用 `add_session_to_memory()`，并在 `LlmAgent` 的 `generate_content_async()` 中（通过 contents 处理器）将检索结果注入 LLM 请求。

**嵌入函数可插拔：** 通过 `VertexAiRagMemoryService` 底层的 RAG Engine 配置，支持不同嵌入模型。

### 6.3 hermes-agent

**核心文件：**
- `agent/memory_manager.py`（`MemoryManager` — 统一管理）
- `agent/memory_provider.py`（`MemoryProvider` ABC）
- `tools/memory_tool.py`（工具：模型直接调用存取记忆）

hermes-agent 的记忆架构分两层：
1. **外部记忆提供者（MemoryProvider）：** 插件式，可接入任何后端（OpenAI Memory、本地文件等），通过 `prefetch_all()` 预取、`sync_all()` 回写
2. **工具级记忆（memory_tool）：** 模型通过 `memory_remember`/`memory_search`/`memory_forget` 工具主动管理记忆

**RAG 注入位置：** `MemoryManager.prefetch_all(user_message)` 在每次 `run_conversation()` 开始时（第 11148 行）调用，将检索结果注入用户消息上下文。

### 6.4 langchain

**核心文件：**
- `libs/core/langchain_core/chat_history.py`（`BaseChatMessageHistory`）
- `libs/core/langchain_core/vectorstores/`（向量存储接口）

LangChain 的记忆系统高度模块化，`BaseChatMessageHistory` 定义了对话历史接口，向量存储通过 `BaseVectorStore` 抽象，支持 Chroma/FAISS/Pinecone 等。

嵌入函数通过 `Embeddings` ABC（`langchain_core/embeddings/`）可插拔，`VectorStore.from_documents(docs, embeddings)` 时注入。

### 6.5 deepagents

**核心文件：**
- `libs/deepagents/deepagents/middleware/memory.py`（`MemoryMiddleware`）

deepagents 通过 `MemoryMiddleware` 将 LangGraph 的 `BaseStore` 接入长期记忆，在每轮对话前自动检索相关记忆并注入 `AgentState`。

### 横向对比表

| 项目 | 向量存储接入 | RAG 注入位置 | 嵌入函数可插拔 |
|------|-------------|--------------|----------------|
| openai-agents | 无内置（需自定义工具） | — | — |
| adk-python | `BaseMemoryService` ABC（Vertex AI RAG 等） | contents 处理器（循环前） | 通过 RAG Engine 配置 |
| hermes-agent | MemoryProvider 插件（任意后端） | `prefetch_all()` 在循环前注入 | 由外部 provider 实现 |
| langchain | `BaseVectorStore` ABC（Chroma/FAISS 等） | 自定义 Runnable 链中 | `Embeddings` ABC |
| deepagents | LangGraph BaseStore | MemoryMiddleware 在每轮注入 | 通过 Store 实现 |

---

## 7. 错误处理与重试

### 7.1 openai-agents-python

**核心文件：**
- `src/agents/retry.py`（`ModelRetrySettings`、`_RetryPolicies`、`RetryPolicy`）
- `src/agents/run_internal/model_retry.py`（`get_response_with_retry()`、`stream_response_with_retry()`）

**重试策略组合器（retry.py 第 231 行）：**

```python
class _RetryPolicies:
    def never(self) -> RetryPolicy: ...
    def provider_suggested(self) -> RetryPolicy: ...   # 遵从 Retry-After 响应头
    def network_error(self) -> RetryPolicy: ...         # 网络错误时重试
    def retry_after(self) -> RetryPolicy: ...           # 解析 Retry-After header
    def http_status(self, statuses: Iterable[int]) -> RetryPolicy: ...
    def all(self, *policies) -> RetryPolicy: ...        # 策略 AND 组合
    def any(self, *policies) -> RetryPolicy: ...        # 策略 OR 组合

retry_policies = _RetryPolicies()  # 全局单例
```

**工具执行异常：** `FunctionTool` 的 `_failure_error_function` 处理工具异常，默认使用 `default_tool_error_function()` 将错误转为模型可见的字符串（`tool.py` 第 1475 行），不会让程序崩溃。超时通过 `asyncio.wait_for()` + `timeout_seconds` 实现（第 1688 行）。

**rate limit 处理：** `model_retry.py` 中的 `_parse_retry_after()` 解析 `Retry-After-Ms` 和 `Retry-After` 响应头，指数退避默认参数：初始 0.25s，最大 2s，倍数 2。

### 7.2 adk-python

**核心文件：**
- `src/google/adk/errors/`（自定义错误类型）
- `src/google/adk/flows/llm_flows/base_llm_flow.py`（重连逻辑）

ADK 在 `base_llm_flow.py` 中实现 Live API 的 WebSocket 重连（第 `DEFAULT_MAX_RECONNECT_ATTEMPTS = 5`），对工具执行异常通过 `try/except` 捕获后在 `FunctionResponse.response` 中返回错误信息给模型。

### 7.3 hermes-agent

**核心文件：**
- `agent/retry_utils.py`（`jittered_backoff()`）
- `agent/error_classifier.py`（`classify_api_error()`，`FailoverReason` 枚举）

```python
# agent/error_classifier.py（简化）
def classify_api_error(exc) -> FailoverReason:
    # 区分：rate_limit / context_length / auth_error / network_error ...
```

hermes-agent 的错误处理极为丰富：区分 rate limit（429）、context length 超出（4xx）、认证错误（401）、网络错误等，针对不同错误类型触发不同行为（降级模型、压缩上下文、失败回退）。

### 7.4 langchain

**核心文件：**
- `libs/core/langchain_core/runnables/retry.py`（`RunnableRetry`）

通过 `tenacity` 库实现：

```python
# retry.py 第 10-18 行
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential_jitter,
)
```

使用方式：`model.with_retry(retry_if_exception_type=(RateLimitError,), stop_after_attempt=3)`

### 7.5 deepagents

deepagents 基于 LangChain 的 `with_retry()` 接口，同时通过 `PatchToolCallsMiddleware` 处理格式错误的工具调用。

### 横向对比表

| 项目 | 重试实现 | Rate Limit 处理 | 工具异常捕获 |
|------|----------|-----------------|--------------|
| openai-agents | 自实现 RetryPolicy 策略组合器 | 解析 Retry-After header，指数退避 | `failure_error_function` 返回字符串给模型 |
| adk-python | WebSocket 重连（Live API） | Google SDK 内置处理 | FunctionResponse.response 返回错误 |
| hermes-agent | `jittered_backoff()` + 模型降级 | classify_api_error 区分 429 | 工具 try/except，大小截断 |
| langchain | `RunnableRetry` (tenacity) | `retry_if_exception_type=(RateLimitError,)` | 工具异常返回字符串或重新抛出 |
| deepagents | 继承 LangChain with_retry | 同 LangChain | `PatchToolCallsMiddleware` 修复格式错误 |

---

## 8. 对外 API 设计

### 8.1 openai-agents-python

**极简程度：**

```python
from agents import Agent, Runner, function_tool

@function_tool
def get_weather(city: str) -> str:
    """Get weather for a city."""
    return f"Sunny in {city}"

agent = Agent(name="assistant", instructions="You are helpful.", tools=[get_weather])
result = await Runner.run(agent, "What's the weather in NYC?")
print(result.final_output)
```

**配置方式：** `Agent` 构造参数（`name`、`instructions`、`model`、`tools`、`output_type`）+ `RunConfig`（全局配置，如 `max_turns`、`model_settings`）。环境变量通过 `openai.OpenAI(api_key=os.environ["OPENAI_API_KEY"])` 传入。

**扩展点：**
- `RunHooks`（`lifecycle.py`）：`on_agent_start`/`on_tool_start`/`on_tool_end` 等生命周期钩子
- `FunctionTool.failure_error_function`：自定义错误处理
- `ModelSettings`：细粒度模型参数覆盖

### 8.2 adk-python

**极简程度：**

```python
from google.adk.agents import LlmAgent
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService

agent = LlmAgent(model="gemini-2.0-flash", name="assistant", instruction="...")
runner = Runner(app_name="app", agent=agent, session_service=InMemorySessionService())

async for event in runner.run_async(user_id="u1", session_id="s1", new_message=...):
    if event.is_final_response():
        print(event.content.parts[0].text)
```

**配置方式：** 构造参数 + `RunConfig` + 环境变量（`GOOGLE_API_KEY`、`GOOGLE_CLOUD_PROJECT` 等）。

**扩展点：** `before_model_callback`/`after_model_callback`/`before_tool_callback`/`after_tool_callback` 四种回调（`llm_agent.py` 第 72-130 行），`BasePlugin` 系统。

### 8.3 hermes-agent

**极简程度：**

```python
from run_agent import AIAgent

agent = AIAgent(base_url="http://localhost:30000/v1", model="gpt-4o")
result = agent.run_conversation("Tell me about Python 3.12")
print(result["response"])
```

**配置方式：** 构造参数（80+ 参数，高度可配置）+ `~/.hermes/.env` 文件 + `cfg_get()` 配置系统。

**扩展点：** `status_callback`/`step_callback` 回调，`MemoryProvider` 插件，`hermes_cli.plugins` hook 系统（`on_session_start`、`pre_llm_call` 等）。

### 8.4 langchain

**极简程度：**

```python
from langchain_openai import ChatOpenAI
from langchain_core.tools import tool
from langchain.agents import create_react_agent, AgentExecutor

@tool
def search(query: str) -> str:
    """Search for information."""
    return "results"

llm = ChatOpenAI(model="gpt-4o")
agent = create_react_agent(llm, tools=[search], prompt=hub.pull("hwchase17/react"))
executor = AgentExecutor(agent=agent, tools=[search])
result = executor.invoke({"input": "What is LangChain?"})
```

**配置方式：** 环境变量（`OPENAI_API_KEY` 等）+ 构造参数 + `RunnableConfig`（运行时注入）。

**扩展点：** `BaseCallbackHandler`（回调系统）、`with_retry()`/`with_fallbacks()`（Runnable 包装器）、`Runnable.configurable_fields()`（运行时动态配置）。

### 8.5 deepagents

**极简程度：**

```python
from deepagents import create_deep_agent
from langchain_anthropic import ChatAnthropic

agent = create_deep_agent(
    model=ChatAnthropic(model_name="claude-sonnet-4-6"),
    tools=[...],
)
result = agent.invoke({"messages": [HumanMessage(content="Do X")]})
```

**配置方式：** `create_deep_agent()` 单函数入口，参数丰富（`tools`、`model`、`system_prompt`、`permissions`、`middleware` 等）。

**扩展点：** `AgentMiddleware` 中间件系统（`FilesystemMiddleware`、`SubAgentMiddleware`、`MemoryMiddleware` 等）。

### 横向对比表

| 项目 | 最少代码行数运行 | 配置组织 | 核心扩展点 |
|------|----------------|----------|------------|
| openai-agents | ~5 行 | 构造参数 + RunConfig | RunHooks + function_tool 装饰器 |
| adk-python | ~8 行（含 session 创建） | 构造参数 + RunConfig + env | 4 类 Callback + Plugin 系统 |
| hermes-agent | ~3 行 | 构造参数（80+）+ .env 文件 | status_callback + MemoryProvider + Plugin |
| langchain | ~8 行（含 prompt/executor） | env + 构造参数 + RunnableConfig | BaseCallbackHandler + with_retry/fallbacks |
| deepagents | ~4 行 | create_deep_agent() 单函数 | AgentMiddleware 中间件栈 |

---

## 对 MyReactAgent 的可借鉴实践

以下是最值得直接借鉴的具体实现，按优先级排序：

### 1. Function Schema 自动生成（最高优先级）

**借鉴自：** openai-agents-python  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/openai-agents-python/src/agents/function_schema.py`

核心思路：
- `generate_func_documentation()` 使用 `griffe` 库解析 Google/numpy/sphinx 三种 docstring 格式
- 通过 `pydantic.create_model()` 动态创建参数模型，再调用 `model_json_schema()` 生成 JSON Schema
- 自动检测第一个参数是否为 `RunContextWrapper` / `ToolContext` 并跳过

对于 MyReactAgent 的 `utils/schema.py`，可以参考此实现，用 pydantic + inspect 替代手动解析，完全覆盖 Phase 1 需求。

### 2. 工具注册与执行的统一封装（高优先级）

**借鉴自：** openai-agents-python  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/openai-agents-python/src/agents/tool.py`（第 282-406 行）

`FunctionTool` dataclass 的设计值得直接参考：
- `on_invoke_tool: Callable[[ToolContext, str], Awaitable[Any]]` — 统一调用接口
- `_failure_error_function` — 工具异常转为可见字符串，防止崩溃
- `asyncio.to_thread()` 将同步工具透明地转为异步调用（`tool.py` 第 1865 行）

```python
# openai-agents 中同步函数的异步化处理
result = await asyncio.to_thread(the_func, *args, **kwargs_dict)
```

MyReactAgent 的 `tools/base.py` 可以借鉴这种同步/异步透明化机制。

### 3. 重试策略组合器（高优先级）

**借鉴自：** openai-agents-python  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/openai-agents-python/src/agents/retry.py`

`_RetryPolicies` 类提供了 `any()`/`all()` 策略组合器，远比简单的 `@retry(max_attempts=3)` 灵活。MyReactAgent 在 Phase 4 中可直接参考此设计实现 `llm/retry.py`。

### 4. 流式 tool_call 碎片组装（Phase 2 重要参考）

**借鉴自：** langchain-core  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/langchain/libs/core/langchain_core/messages/`（AIMessageChunk）

LangChain 通过 `AIMessageChunk.__add__()` 实现 tool_call delta 合并，按 `index` 拼接 `name` 和 `args` 字段的方式清晰实用。MyReactAgent 的 `llm/streaming.py` 可直接参考此模式实现 `StreamingHandler`。

### 5. AgentTool（子 Agent 包装）模式（Phase 2 重要参考）

**借鉴自：** adk-python  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/adk-python/src/google/adk/tools/agent_tool.py`（第 94-286 行）

ADK 的 `AgentTool` 实现展示了：
- 子 Agent 创建独立 Session 运行
- 状态通过 `tool_context.state.update()` 双向同步
- 最后一条内容作为工具返回值

MyReactAgent 的 `agent/orchestrator.py` 中的 `AgentTool` 可以参考此实现，核心逻辑约 50 行。

### 6. 线程安全的 ToolRegistry（工具注册表）

**借鉴自：** hermes-agent  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/hermes-agent/tools/registry.py`（第 143-260 行）

hermes-agent 的 ToolRegistry 用 `threading.RLock` + `_generation` 计数器实现线程安全和缓存失效，适合 MyReactAgent 在 Phase 2 引入异步后保证并发安全。

### 7. NextStep 枚举模式（核心循环控制）

**借鉴自：** openai-agents-python  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/openai-agents-python/src/agents/run_internal/run_steps.py`（第 144-181 行）

将循环的每一步结果封装为枚举类型（`NextStepRunAgain`/`NextStepFinalOutput`/`NextStepHandoff`/`NextStepInterruption`），使循环控制流清晰可读。MyReactAgent 的 `agent/react_agent.py` 循环可以参考此模式，取代原始的 `if finish_reason == "stop"` 判断。

### 8. 上下文压缩策略（Phase 3 长期记忆）

**借鉴自：** hermes-agent  
**文件：** `/Users/tanglin/VibeCoding/MyReactAgent/reference_projects/hermes-agent/agent/context_compressor.py` 和 `run_agent.py` 第 11005-11063 行

hermes-agent 的预飞行压缩（preflight compression）策略：先估算 token 数，超阈值时触发 LLM 摘要，保护首尾 N 条消息。这直接对应 MyReactAgent 宪法第 13 条「框架内置上下文窗口管理」。

---

## 调研补充：LangGraph 源码深度分析

> **调研时间**：2026-05-08（补充）  
> **仓库来源**：`reference_projects/langgraph/`（shallow clone，commit HEAD）  
> **调研目的**：补全五大主流框架中唯一缺失的 LangGraph 源码参考

---

### 一、仓库结构总览

LangGraph 采用 **monorepo** 结构，各功能组件以独立 Python 包形式存放于 `libs/`：

```
reference_projects/langgraph/
├── libs/
│   ├── langgraph/          # 核心框架：图定义、执行引擎、类型系统
│   │   └── langgraph/
│   │       ├── graph/      # StateGraph、CompiledStateGraph
│   │       ├── pregel/     # BSP 执行引擎（_loop.py、_algo.py 等）
│   │       ├── channels/   # Channel 系统（LastValue、BinaryOperatorAggregate）
│   │       ├── types.py    # 核心类型：StreamMode、Command、interrupt、RetryPolicy
│   │       ├── constants.py# START、END、TAG_HIDDEN 等常量
│   │       └── runtime.py  # Runtime 上下文注入
│   ├── checkpoint/         # 持久化基础接口（BaseCheckpointSaver、Checkpoint）
│   ├── checkpoint-postgres/# PostgreSQL 持久化实现
│   ├── checkpoint-sqlite/  # SQLite 持久化实现
│   ├── prebuilt/           # 高层 API：ToolNode、create_react_agent（已迁移）
│   ├── cli/                # LangGraph CLI 工具
│   └── sdk-py/             # LangGraph Server Python SDK
```

**关键依赖图**（`libs/checkpoint` 是基础，其余依赖它）：
```
checkpoint → checkpoint-postgres, checkpoint-sqlite, prebuilt, langgraph
prebuilt   → langgraph（高层 API 层）
```

---

### 二、核心执行引擎：Pregel BSP 模型

**核心文件：**
- `libs/langgraph/langgraph/pregel/_loop.py`（循环控制器）
- `libs/langgraph/langgraph/pregel/_algo.py`（`prepare_next_tasks`、`apply_writes`、`should_interrupt`）
- `libs/langgraph/langgraph/pregel/main.py`（Pregel 入口，`invoke`/`stream`）

LangGraph 的执行引擎基于 **Pregel BSP（Bulk Synchronous Parallel）** 模型：图中的节点在每个 **super-step** 内并行执行，完成后统一写入 Channel，再进入下一个 super-step。

```python
# _loop.py 导入的核心函数
from langgraph.pregel._algo import (
    Call,
    GetNextVersion,
    PregelTaskWrites,
    apply_writes,           # 将节点输出写入 Channel
    prepare_next_tasks,     # 根据 Channel 版本决定哪些节点进入下一 super-step
    should_interrupt,       # 检查是否触发 interrupt_before/interrupt_after
    prepare_single_task,    # 准备单个节点任务
)
```

**与 ReAct 循环的对应关系：**

| ReAct 步骤 | LangGraph 实现 |
|----------|--------------|
| 调用 LLM | agent 节点（super-step） |
| 检测 tool_calls | `should_continue` 条件边 |
| 执行工具 | tools 节点（super-step） |
| 写回 ToolMessage | `apply_writes` → messages Channel |
| 判断终止 | `prepare_next_tasks` 返回空任务列表 |

---

### 三、StateGraph 编译过程与 Channel 系统

**核心文件：** `libs/langgraph/langgraph/graph/state.py`（`__all__ = ("StateGraph", "CompiledStateGraph")`）

StateGraph 是**声明式构建器**，`compile()` 后转换为可执行的 `Pregel` 实例：

```python
# state.py 关键导入揭示了内部机制
from langgraph.channels.binop import BinaryOperatorAggregate   # Reducer（如 add_messages）
from langgraph.channels.last_value import LastValue             # 默认 Channel（覆盖语义）
from langgraph.channels.ephemeral_value import EphemeralValue  # 一次性值 Channel
from langgraph.pregel import Pregel                             # 编译目标
from langgraph.pregel._read import ChannelRead, PregelNode     # 节点读取原语
from langgraph.pregel._write import ChannelWrite, ChannelWriteEntry  # 节点写入原语
```

**Channel 系统核心设计：**

State schema 中的每个键都是一个 Channel：
- **无 Reducer 注解** → `LastValue`（后写覆盖前写）
- **`Annotated[list, add_messages]`** → `BinaryOperatorAggregate`（追加合并）
- **`Annotated[..., operator.add]`** → 任意 reduce 函数

```python
# 示例：State 定义如何映射到 Channel
class AgentState(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]  # BinaryOperatorAggregate
    counter: int                                           # LastValue
```

---

### 四、ToolNode 与工具执行设计

**核心文件：** `libs/prebuilt/langgraph/prebuilt/tool_node.py`

`ToolNode` 是 LangGraph 的官方工具执行节点，设计亮点：

**1. 并行执行多个 tool_call：**

```python
# tool_node.py 关键设计：
# - 一次 LLM 调用可能产生多个 tool_calls，ToolNode 并行执行
# - 使用 asyncio 或 ThreadPoolExecutor 并行
```

**2. `ToolCallRequest` 拦截器模式：**

```python
# tool_node.py L132-200
@dataclass
class ToolCallRequest:
    tool_call: ToolCall      # LLM 生成的工具调用
    tool: BaseTool | None    # 已注册的工具实例（未注册时为 None）
    state: Any               # 当前图状态（可注入到工具）
    runtime: ToolRuntime     # 运行时上下文

    def override(self, **overrides) -> ToolCallRequest:
        """不可变模式：返回新实例而非修改原实例"""
        return replace(self, **overrides)
```

**3. 错误模板化（不崩溃原则）：**

```python
# tool_node.py L108-121
INVALID_TOOL_NAME_ERROR_TEMPLATE = (
    "Error: {requested_tool} is not a valid tool, try one of [{available_tools}]."
)
TOOL_CALL_ERROR_TEMPLATE = "Error: {error}\n Please fix your mistakes."
TOOL_EXECUTION_ERROR_TEMPLATE = (
    "Error executing tool '{tool_name}' with kwargs {tool_kwargs} with error:\n"
    " {error}\n Please fix the error and try again."
)
```

所有工具错误均被模板化为字符串 ToolMessage 返回，**绝不让异常崩溃 ReAct 循环**。

**4. State 注入（`InjectedState`）：**

```python
# 工具可以直接访问图状态
from langgraph.prebuilt import InjectedState, InjectedStore

@tool
def my_tool(query: str, state: Annotated[AgentState, InjectedState]) -> str:
    # 直接访问当前图状态，无需通过参数传递
    return f"User: {state['user_id']}, query: {query}"
```

---

### 五、create_react_agent 设计（v1 → v2 迁移）

**核心文件：** `libs/prebuilt/langgraph/prebuilt/chat_agent_executor.py`

**重要发现**：`create_react_agent` 在 LangGraph v1.x 中已被 `@deprecated` 标记，API 已迁移至 `langchain.agents.create_agent`（LangGraph v1.0 重大重构）：

```python
# chat_agent_executor.py L274-277
@deprecated(
    "create_react_agent has been moved to `langchain.agents`. "
    "Please update your import to `from langchain.agents import create_agent`.",
    category=LangGraphDeprecatedSinceV10,
)
def create_react_agent(model, tools, *, prompt=None, response_format=None,
                       pre_model_hook=None, post_model_hook=None, ...):
```

这说明 LangGraph 在 v1.0 进行了重大重构，将 ReAct Agent 的高层 API 上移至 langchain 包，自身专注底层图执行引擎。

**v2 API 的关键新增参数：**

```python
create_react_agent(
    model,
    tools,
    pre_model_hook=...,    # 模型调用前的中间件钩子
    post_model_hook=...,   # 模型调用后的中间件钩子
    context_schema=...,    # 运行时上下文类型（Runtime[ContextT]）
    version="v2",          # v2 使用新的 Runtime 注入机制
)
```

**`Prompt` 类型的灵活性：**

```python
# chat_agent_executor.py L121-126
Prompt = (
    SystemMessage
    | str
    | Callable[[StateSchema], LanguageModelInput]    # 可以是函数，动态生成 prompt
    | Runnable[StateSchema, LanguageModelInput]       # 可以是 Runnable，支持链式组合
)
```

这比简单的 `system_prompt: str` 抽象层次更高，适合 MyReactAgent Phase 4 的扩展。

---

### 六、Checkpoint 持久化架构

**核心文件：** `libs/checkpoint/langgraph/checkpoint/base/__init__.py`

**`Checkpoint` 数据结构（`base/__init__.py` L83-114）：**

```python
class Checkpoint(TypedDict):
    v: int                           # 格式版本，当前为 1
    id: str                          # 单调递增 ID（用于排序）
    ts: str                          # ISO 8601 时间戳
    channel_values: dict[str, Any]   # 各 Channel 的快照值
    channel_versions: ChannelVersions# Channel 版本号（用于 BSP 调度决策）
    versions_seen: dict[str, ChannelVersions]  # 各节点已处理的 Channel 版本
    updated_channels: list[str] | None         # 本次更新的 Channel 列表
```

**`BaseCheckpointSaver` 核心接口（`base/__init__.py` L167-363）：**

```python
class BaseCheckpointSaver(Generic[V]):
    serde: SerializerProtocol = JsonPlusSerializer()  # 默认 JSON+ 序列化

    # ---- 必须实现的抽象方法 ----
    def get_tuple(self, config) -> CheckpointTuple | None: ...  # 获取检查点
    def list(self, config, *, filter, before, limit) -> Iterator[CheckpointTuple]: ...  # 列举历史
    def put(self, config, checkpoint, metadata, new_versions) -> RunnableConfig: ...    # 存储快照
    def put_writes(self, config, writes, task_id, task_path="") -> None: ...            # 存储增量写入

    # ---- 可选实现（运维功能）----
    def delete_thread(self, thread_id) -> None: ...     # 删除线程所有检查点
    def copy_thread(self, src_id, tgt_id) -> None: ...  # 复制线程（时间旅行分支）
    def prune(self, thread_ids, *, strategy) -> None: ... # 裁剪历史
```

**`CheckpointMetadata` 字段含义（`base/__init__.py` L38-77）：**

```python
class CheckpointMetadata(TypedDict, total=False):
    source: Literal["input", "loop", "update", "fork"]  # 检查点来源
    step: int          # -1 = 初始输入, 0 = 第一次 loop, N = 第 N+1 次
    parents: dict[str, str]  # 父检查点 ID（namespace → checkpoint_id）
    run_id: str        # 本次运行的唯一 ID
```

**`CheckpointTuple` 结构（`base/__init__.py` L130-137）：**

```python
class CheckpointTuple(NamedTuple):
    config: RunnableConfig          # 包含 thread_id、checkpoint_id
    checkpoint: Checkpoint          # 完整状态快照
    metadata: CheckpointMetadata    # 元数据
    parent_config: RunnableConfig | None  # 父检查点配置
    pending_writes: list[PendingWrite] | None  # 待写入操作（故障恢复用）
```

**关键设计：`put_writes` 是增量容错机制**

节点执行过程中若崩溃，`pending_writes` 保存了已完成的部分写入，重启后可跳过已执行的节点。这是 LangGraph 实现 "exactly-once" 语义的核心。

---

### 七、Human-in-the-Loop：interrupt() 与 Command

**核心文件：** `libs/langgraph/langgraph/types.py`（L520-870）

**`interrupt()` 函数（types.py L801-867）：**

```python
def interrupt(value: Any) -> Any:
    """
    关键行为：
    1. 第一次调用 → 抛出 GraphInterrupt 异常，暂停执行，value 传递给客户端
    2. 客户端用 Command(resume=...) 恢复时 → 从节点起点重新执行
    3. 同一节点内多次 interrupt() → 按调用顺序匹配 resume 值
    4. 必须配合 checkpointer 使用（依赖持久化状态）
    """
    raise GraphInterrupt(Interrupt(value=value))
```

**节点重执行机制（重要）：** 节点被 resume 时**从头重新执行**，不是从 interrupt 调用处继续。这意味着节点中 interrupt 之前的副作用操作会被重复执行，开发者必须做幂等性保证。

**`Interrupt` 数据结构（types.py L524-578）：**

```python
@final
@dataclass(init=False, slots=True)
class Interrupt:
    value: Any   # 发送给客户端的信息（可以是任意对象）
    id: str      # 中断标识符（xxhash 生成，用于多 interrupt 场景匹配）
```

**`Command` 类型（types.py L748-798）：**

```python
@dataclass(frozen=True)
class Command(Generic[N]):
    graph: str | None = None   # None=当前图, Command.PARENT=父图
    update: Any | None = None  # 更新状态的值（dict 或 Pydantic 模型）
    resume: dict[str, Any] | Any | None = None  # 恢复 interrupt 的值
    goto: Send | Sequence[Send | N] | N = ()    # 跳转到指定节点

    PARENT: ClassVar[Literal["__parent__"]] = "__parent__"
```

**`Send` 类型——Map-Reduce 专用（types.py L654-742）：**

```python
class Send:
    """在条件边中动态发送消息到特定节点（支持 Map-Reduce 模式）"""
    node: str        # 目标节点名
    arg: Any         # 发送的状态/消息
    timeout: TimeoutPolicy | None  # 可选超时策略

# 使用示例（Map-Reduce）：
def continue_to_jokes(state: OverallState):
    return [Send("generate_joke", {"subject": s}) for s in state["subjects"]]
    # 每个 subject 并行触发一个 generate_joke 节点实例
```

---

### 八、流式实现：7 种 StreamMode

**核心文件：** `libs/langgraph/langgraph/types.py`（L120-134）

LangGraph 定义了 7 种流式模式（`StreamMode` 类型别名）：

```python
StreamMode = Literal[
    "values",      # 每步后发送完整状态快照
    "updates",     # 每步后仅发送本步变更（节点名 → 输出）
    "custom",      # 节点内通过 StreamWriter 主动推送任意数据
    "messages",    # token 级流式（LLM 生成过程中逐 token 推送）
    "checkpoints", # checkpoint 事件（等价于 get_state() 格式）
    "tasks",       # 任务启动/完成事件（含错误信息）
    "debug",       # 调试模式（= checkpoints + tasks 合并）
]
```

**各 StreamPart 的数据结构（types.py L252-341）：**

```python
class ValuesStreamPart(TypedDict):
    type: Literal["values"]
    ns: tuple[str, ...]    # 节点命名空间（支持子图路径）
    data: OutputT          # 完整状态值
    interrupts: tuple[Interrupt, ...]

class UpdatesStreamPart(TypedDict):
    type: Literal["updates"]
    ns: tuple[str, ...]
    data: dict[str, Any]   # {节点名: 该节点的输出}

class MessagesStreamPart(TypedDict):
    type: Literal["messages"]
    ns: tuple[str, ...]
    data: tuple[AnyMessage, dict[str, Any]]  # (消息/chunk, 元数据)
    # 元数据包含：langgraph_step, langgraph_node, langgraph_triggers 等

class CustomStreamPart(TypedDict):
    type: Literal["custom"]
    data: Any              # StreamWriter 推送的任意值
```

**v2 流式 API（`version="v2"`）：** 返回 `StreamPart` 鉴别联合类型，通过 `part["type"]` 区分，类型安全。

---

### 九、RetryPolicy 与错误处理

**核心文件：** `libs/langgraph/langgraph/types.py`（L406-426）

```python
class RetryPolicy(NamedTuple):
    initial_interval: float = 0.5   # 首次重试等待（秒）
    backoff_factor: float = 2.0     # 指数退避系数
    max_interval: float = 128.0     # 最大等待时间（秒）
    max_attempts: int = 3           # 最大重试次数（含首次）
    jitter: bool = True             # 随机抖动（防止惊群）
    retry_on: (
        type[Exception]
        | Sequence[type[Exception]]
        | Callable[[Exception], bool]
    ) = default_retry_on            # 重试条件（可自定义为函数）
```

`retry_on` 支持传入可调用对象，这意味着可以实现复杂的重试条件逻辑（如区分 rate_limit vs auth error）。

**`TimeoutPolicy` 两档超时（types.py L439-501）：**

```python
@dataclass(frozen=True)
class TimeoutPolicy:
    run_timeout: float | None = None   # 硬超时（不可被活动信号刷新）
    idle_timeout: float | None = None  # 空闲超时（有活动时自动刷新）
    refresh_on: Literal["auto", "heartbeat"] = "auto"
```

两档超时区分「总时长」和「空闲时长」，适合长时间工具调用场景。

---

### 十、对 MyReactAgent 各阶段的关键启示

#### Phase 1：零全局状态 + 工具错误 Observation 化

LangGraph 的 `ToolNode` 彻底验证了「工具错误转 ToolMessage 返回」的正确性：
- `TOOL_CALL_ERROR_TEMPLATE`、`TOOL_INVOCATION_ERROR_TEMPLATE` 等 4 个错误模板（`tool_node.py` L108-121）
- 未注册工具名同样返回友好错误字符串而非抛异常

**直接参考**：`reference_projects/langgraph/libs/prebuilt/langgraph/prebuilt/tool_node.py`（L108-121）

#### Phase 2：Channel 系统 vs 直接消息传递

LangGraph 的 `add_messages` reducer 模式（`Annotated[list, add_messages]`）是消息追加的显式声明。MyReactAgent 可以参考此模式，在 `memory/short_term.py` 中明确声明消息追加语义而非直接 `list.append()`。

**直接参考**：`reference_projects/langgraph/libs/langgraph/langgraph/graph/message.py`（`add_messages` 函数实现）

#### Phase 3：Checkpoint 接口设计

`BaseCheckpointSaver` 的 4 个核心方法（`get_tuple`/`list`/`put`/`put_writes`）是最精炼的持久化抽象。尤其是 `put_writes` 的增量设计——先存增量，定期合并快照——适合 MyReactAgent 的 `memory/checkpoint.py` 接口设计。

**直接参考**：`reference_projects/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py`（L167-363）

#### Phase 4：interrupt() 的节点重执行陷阱

LangGraph 的 `interrupt()` 在恢复时**从节点起点重新执行**，这意味着 interrupt 前的副作用会被重复触发。MyReactAgent 实现 HITL 时需要遵循同样的幂等性约束，即「HITL 节点内所有副作用操作必须是幂等的」。

**直接参考**：`reference_projects/langgraph/libs/langgraph/langgraph/types.py`（L801-870，`interrupt()` 函数及文档）

#### Phase 4：RetryPolicy 的 retry_on 可调用设计

`retry_on: Callable[[Exception], bool]` 比简单的异常类型列表更灵活，支持在运行时动态判断是否重试（如解析 HTTP 状态码）。MyReactAgent 的 `llm/retry.py` 应支持同样的接口。

**直接参考**：`reference_projects/langgraph/libs/langgraph/langgraph/types.py`（L406-426，`RetryPolicy` NamedTuple）
