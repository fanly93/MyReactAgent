# Research: Phase 1 MVP — ReAct Agent 核心框架

**Feature**: `001-phase1-mvp-prototype`  
**生成时间**: 2026-05-08  
**状态**: 完成（无 NEEDS CLARIFICATION 项，规范已充分明确）

---

## 1. OpenAI SDK 同步流式输出

**Decision**: 使用 `stream=True` 参数，返回值为同步 `Stream[ChatCompletionChunk]`，通过 `for chunk in stream:` 迭代，无需 `async/await`。

**Rationale**: Phase 1 约束为全同步执行。OpenAI SDK 的 `client.chat.completions.create(stream=True)` 返回同步迭代器，天然满足约束，且 API 与非流式接口对称，简化了 LLMClient 的接口设计。

**关键实现细节**:
- `chunk.choices[0].delta.content` 包含当前文本片段（可能为 `None`）
- `chunk.choices[0].delta.tool_calls` 包含工具调用增量（按 `index` 累积）
- `chunk.choices[0].finish_reason` 仅在最后一个非空 chunk 中设置（`"stop"` 或 `"tool_calls"`）
- 流式结束后需重建完整 `tool_calls` 列表：按 `index` 合并 `id`、`function.name`、`function.arguments`（增量字符串拼接）
- `on_llm_start` 在请求发送前触发；`on_llm_end` 在流结束、内容拼接完成后触发（携带完整内容）

**Alternatives considered**:
- 使用 `httpx` 直接调用 API 实现流式：需自行处理重试、认证、错误解析，远超实现成本；`openai` SDK 已内置，选 SDK。
- 将 `run()` 和 `run_stream()` 合并为同一方法：`run()` 同步返回字符串更符合学习场景直觉；`run_stream()` 返回迭代器；两者接口语义清晰，不合并。

---

## 2. `@tool` 装饰器实现方案

**Decision**: 通过 `inspect.signature()` + `typing.get_type_hints()` 提取参数，使用 `pydantic.create_model()` 动态生成验证模型，`model.model_json_schema()` 生成 OpenAI 兼容的 JSON Schema。

**Rationale**: Pydantic v2 原生支持 `create_model()` 动态建模和 `model_json_schema()` 标准 JSON Schema 输出，与 OpenAI Tool Use 接口完全兼容，无需手写 Schema 转换逻辑。

**关键实现细节**:
```
1. inspect.signature(func)  → 获取参数名、默认值
2. typing.get_type_hints(func)  → 获取参数类型注解（解析字符串注解）
3. 过滤掉 `return` 和 `self`
4. 对无类型注解的参数默认为 `str`
5. pydantic.create_model("ArgsModel", **{name: (type, FieldInfo(description=...))})
6. model.model_json_schema() → {"type": "object", "properties": {...}, "required": [...]}
7. 工具名 = func.__name__（将下划线保留，不转换）
8. 工具描述 = func.__doc__ 第一行（strip 后）
```

**装饰器 vs 类继承**:
- `@tool`：适合简单函数，自动生成 Schema（FR-008）
- `class MyTool(BaseTool)`：完全手动控制，用于复杂场景（FR-009）
- 两者共享相同的 `BaseTool` 抽象基类，`ToolRegistry` 对两者一视同仁

**Alternatives considered**:
- 使用 `dataclasses` 替代 Pydantic：缺乏 JSON Schema 生成能力，需额外实现，放弃。
- 使用 `jsonschema` 库手写 Schema：增加依赖且需维护 Schema 与类型注解同步，放弃。

---

## 3. OpenAI Tool Call 响应解析

**Decision**: 非流式直接读取 `message.tool_calls`；流式通过按 `index` 累积增量重建。解析失败（无效 JSON）触发 `on_error` 回调并作为 `ToolResult(success=False)` 返回。

**Rationale**: OpenAI API 协议保证 `tool_calls` 格式，但 LLM 生成的 `function.arguments` 偶尔包含格式错误的 JSON（截断或非法字符），必须防御性处理，不得导致 agent 循环崩溃（FR-011、宪法 III）。

**关键实现细节**:
- 非流式 `message.to_dict()` 后直接序列化存入对话历史（避免 SDK 对象耦合）
- 流式 tool_calls 重建：维护 `dict[int, dict]` 按 index 累积，流结束后转为标准结构
- `function.arguments` 用 `json.loads()` 解析，捕获 `json.JSONDecodeError`
- 解析失败时：发出 `on_error` 事件，将错误消息作为 tool 结果返回给模型（允许模型修正参数）

---

## 4. 滑动窗口截断算法

**Decision**: 按消息条数截断（非 token），分三类保护区，仅截断保护区外的中间普通对话消息。

**Rationale**: Phase 1 用字符数近似 token 计数（宪法 XIII 允许，Phase 3+ 才引入 tiktoken）。分类保护算法直接对应 FR-006 精确规定，实现逻辑清晰可测试。

**截断算法（按优先级）**:
```
输入: messages (list), max_messages (int), keep_last_n (int)

1. 提取 system_messages = [m for m in messages if m.role == "system"]
   （永远置于首位，不参与计数和截断）

2. 提取 non_system = messages where role != "system"

3. 识别 tool_call_pairs（原子单元，不得拆开）：
   遍历 non_system，找到 role=assistant 且 tool_calls 非空的消息，
   将其与紧随其后所有 role=tool 的消息组成一个"保护组"

4. 识别 last_n_rounds（keep_last_n 轮完整对话，从末尾向前数）：
   一"轮" = 1 条 user 消息 + 1 条 assistant 回复；
   向前扫描 non_system 消息，累计到 keep_last_n 轮时停止，
   标记这部分为受保护的 last_rounds_protected

5. 受保护的消息集合 = tool_call_pairs ∪ last_rounds_protected

6. 可截断区 = non_system 中不在受保护集合的消息（中间的普通对话）

7. while len(system_messages) + len(non_system) > max_messages:
       if 可截断区为空: break  # 无法继续截断，警告后保留现状
       从可截断区移除最旧的 1 条
```

**Alternatives considered**:
- Token 计数截断（tiktoken）：Phase 1 可读性优先，消息条数近似已够用；Phase 3 升级。
- 直接截断前 N 条（不保护工具配对）：会破坏工具调用 assistant/tool 消息对，导致 OpenAI API 报错（tool_call_id 未匹配），放弃。

---

## 5. Pydantic v2 工具参数验证

**Decision**: 使用 `ArgsModel.model_validate(args_dict)` 验证，捕获 `ValidationError` 转化为 `ToolResult(success=False, error=str(e))`。

**Rationale**: 与工具 Schema 生成使用同一个 Pydantic 模型，保证声明与验证的一致性（宪法 XIV）。

**关键实现细节**:
- `ToolRegistry.execute(name, args_dict)` 是唯一的工具执行入口
- 验证在 dispatch 到具体工具 `execute()` 方法之前完成
- `ValidationError` 的 `errors()` 列表序列化为 JSON 字符串作为错误信息
- 工具 `execute()` 抛出的任意异常被 `try/except Exception` 捕获，同样转化为 `ToolResult(success=False)`

---

## 6. 会话隔离实现策略

**Decision**: `ReactAgent` 构造时创建独立的 `ConversationMemory` 和 `ToolRegistry` 实例；`session_id` 通过 `str(uuid.uuid4())` 自动生成，支持自定义。

**Rationale**: 零全局可变状态（宪法 XII）。每个 `ReactAgent` 实例是完全独立的，工厂模式（`AgentFactory` 或直接 `ReactAgent(...)` 构造）按需生成会话。

**关键实现细节**:
- 禁止使用任何 `@classmethod` 或 `class-level` 可变属性
- `run_id = str(uuid.uuid4())` 在每次 `run()` / `run_stream()` 开始时生成
- `session_id` 与 Agent 实例绑定，在实例生命周期内不变
- 并发 10 个会话测试（SC-004）：各自实例化 `ReactAgent`，历史消息不会交叉

---

## 7. 回调事件分发机制

**Decision**: `ReactAgent` 持有 `list[BaseCallbackHandler]`，内部 `_emit(event: CallbackEvent)` 方法遍历调用对应处理器方法，核心循环代码只调用 `_emit()`。

**Rationale**: 核心代码不含 trace 逻辑（宪法 VI）；`BaseCallbackHandler` 每个方法有默认空实现，子类只需覆盖关心的事件。

**事件触发点**:
```
run() 开始    → on_agent_start
LLM 请求前   → on_llm_start
LLM 响应后   → on_llm_end
工具执行前   → on_tool_start（每个工具调用触发一次）
工具执行后   → on_tool_end（每个工具调用触发一次）
run() 结束   → on_agent_end
任意异常处   → on_error
```

---

## 8. 项目包结构决策

**Decision**: 包名 `myreactagent`，目录结构遵循宪法 IV 层次边界：`schemas/` → `tools/` → `llm/` + `memory/` → `callbacks/` → `agent/`。

**Rationale**: `schemas/` 作为跨层共享的纯数据类型层（无业务逻辑），可被任意层导入而不违反层次约束。`callbacks/` 在 `llm/memory/` 之上因为 `BaseCallbackHandler` 被 `agent/` 层使用。

**关键决策**:
- `schemas/` 替代 `utils/`：Phase 1 没有通用工具函数，只有数据类型定义；`utils/` 留给 Phase 2+ 的辅助函数
- Pydantic `BaseModel` 用于所有跨模块边界的数据结构（`Message`、`ToolResult`、`CallbackEvent`）
- 不使用 `dataclass`（缺乏内置验证）；不使用 `TypedDict`（缺乏 `.model_validate()` 方法）
