<!--
同步影响报告
============
版本变更：1.0.0 → 1.1.0 → 1.1.1 → 1.2.0 → 1.3.0 → 1.3.1
版本说明：
  1.1.0：基于竞品调研报告细化 4 条已有原则，新增原则 XVII。
  1.1.1：去除宪法中引用的具体实现细节（内部方法名、文件路径、代码块），改为约束性描述。
  1.2.0：原则 VI 将 Callback Hook 名称对齐 spec：on_llm_call → on_llm_start、on_llm_response → on_llm_end、on_tool_call → on_tool_start、on_tool_result → on_tool_end。
  1.3.0：原则 VI 将钩子名称 on_agent_finish 改为 on_agent_end；原则 IX 新增 Phase 1 豁免子句（SDK max_retries=3 满足基础重试要求）。
  1.3.1：原则 VII 明确区分"Phase 1 Python 回调层事件名"与"Phase 4 SSE 协议层事件名"两套命名体系，消除之前版本中两层命名混用导致的歧义；ReactAgent 新增 api_key 构造参数（宪法 III 显式配置要求）。

修改原则（1.1.0）：
  - VII（统一事件格式）：envelope 新增 run_id / span_id 字段；事件类型补充 memory_read / memory_write
  - IX（自动重试与降级）：补全 Jitter 公式；新增错误分类处理策略
  - XI（Human-in-the-Loop）：补充 is_destructive 无 HITL 处理器时必须抛异常；明确 thread_id 持久化游标设计
  - XIII（上下文窗口管理）：新增截断保护规则；新增增量摘要策略

新增原则（1.1.0）：
  - XVII（ReAct 循环终止规范）：主终止信号 / 安全兜底 / NextStep 枚举模式

修改原则（1.1.1）：
  - VI：`self._emit()` 内部方法名 → 描述性文字
  - IX：`llm/client.py` / `tools/registry.py` 文件路径 → 层级描述
  - X：模块-测试文件路径对应表 → 层级约束描述
  - XIV：`ToolRegistry.execute()` 方法名 → 描述性文字
  - XVII：Python 代码块（具体类名）→ 描述性约束

删除章节：无

已更新模板：
  ✅ .specify/memory/constitution.md         — 本文件

待办事项：plan-template.md 中的宪法检查项可在下一次 speckit-constitution 运行时同步更新（新增 XVII 条）。
-->

# MyReactAgent Constitution

## Core Principles

### I. 可读性优先（Readability First）

Code clarity MUST take priority over premature optimization at every phase.
Each development phase has its own quality bar:
- **Phase 1–2 (MVP)**: Code MUST be readable by someone learning agent internals for the first time; favor explicit loops over clever abstractions.
- **Phase 3–4 (Production)**: Performance optimizations are permitted only when profiled and documented; the optimization MUST not obscure the algorithm's intent.

Every public class, function, and module MUST be self-describing through naming alone. Comments are reserved for non-obvious invariants or workarounds, not descriptions of what the code does.

### II. 最小化依赖（Minimal Dependencies）

Every external dependency MUST satisfy at least one of these criteria before being added:
1. The feature is impossible or prohibitively complex without it (e.g., `openai` SDK).
2. It replaces more than 200 lines of correctness-critical code (e.g., `pydantic` for validation).
3. It is an officially endorsed integration target (e.g., `chromadb` for vector storage).

Convenience-only dependencies (pretty printing, config helpers, etc.) MUST NOT be added to core packages. They MAY appear in optional extras (`pyproject.toml [optional-dependencies]`). The dependency list MUST be reviewed at every phase boundary.

### III. 显式优于隐式（Explicit over Implicit）

The framework MUST NOT use magic. Specifically:
- Tool registration MUST be explicit: `registry.register(tool)` or `@tool` decorator — no auto-discovery by import side effects.
- Agent behavior MUST be traceable: every Thought, Action, and Observation MUST be accessible via `verbose=True` or the Callback Hook system.
- Configuration MUST be passed explicitly (constructor arguments or config objects); no hidden global config singletons.
- Errors MUST surface as typed exceptions with descriptive messages, never silently swallowed.

### IV. 层次边界不可越界（Layer Boundary Enforcement）

The codebase MUST maintain a strict unidirectional dependency graph:

```
utils → tools → llm/memory → agent → orchestrator → server (Phase 4)
```

- No layer MAY import from a layer above it.
- No layer MAY skip a layer and import directly from two levels up.
- The `server` / API layer (Phase 4) is the ONLY layer permitted to depend on web frameworks (FastAPI, etc.).
- Violations MUST be caught in code review and treated as blocking defects.

### V. 分阶段迭代（Phased Iteration with Interface Reservation）

The project MUST evolve through four explicit phases, each with a defined completion gate:

| Phase | Scope | Completion Gate |
|-------|-------|----------------|
| **1 — MVP** | Single Agent + Tool calling (sync) | `examples/01_basic_tool_use.py` runs end-to-end |
| **2 — Streaming + Multi-Agent** | Async streaming, OrchestratorAgent | `examples/03_streaming_agent.py` + `examples/04_multi_agent.py` pass |
| **3 — Memory** | Short-term + Long-term vector memory | `examples/02_memory_agent.py` demonstrates cross-session recall |
| **4 — Production** | Observability, HITL, server layer, MCP | All examples pass; API server runs; feature-parity checklist vs. LangChain/OpenAI Agents signed off |

Interfaces for components used in later phases (e.g., `LongTermMemory`, `BaseCallbackHandler`, `LLMClient`) MUST be defined as Python ABCs from Phase 1, even if the Phase 1 implementation is a stub or no-op. Refactoring a stable interface is a constitution violation.

### VI. Callback Hook 可观测性（Non-Intrusive Observability）

Every agent lifecycle event MUST be surfaced through a `BaseCallbackHandler` interface, not scattered as `print()` or logging calls throughout core logic. Required lifecycle hooks:

`on_agent_start` · `on_llm_start` · `on_llm_end` · `on_tool_start` · `on_tool_end` · `on_agent_end` · `on_error`

Core agent code MUST only call the framework's internal event dispatch method at these points — one call per event, no business logic inside the emit path. All logging, tracing, metrics, and LangSmith-style instrumentation MUST be implemented as `BaseCallbackHandler` subclasses, never in the agent loop itself. Phase 1 MUST ship a `ConsoleCallbackHandler` as the default; Phase 4 MUST add an `OpenTelemetryCallbackHandler`.

### VII. 统一事件格式与前端集成（Unified Event Format & Frontend Integration）

All agent runtime events MUST conform to a single JSON envelope from Phase 1 onward:

```json
{"event": "<type>", "data": {…}, "timestamp": "<ISO-8601>", "session_id": "<uuid>", "run_id": "<uuid>", "span_id": "<otel-span-id>"}
```

- `session_id`: 标识一次用户会话（跨多轮对话）
- `run_id`: 标识单次 `agent.run()` 调用（一个 session 可包含多个 run）
- `span_id`: OpenTelemetry span 标识，Phase 1 可留空字符串，Phase 4 接入 OTel 时填充，**Schema 不变**

**两层命名体系（Phase 1 → Phase 4 演进）**：

- **Phase 1 — Python 回调层**（`CallbackEvent.event` 字段当前使用值）：`on_agent_start` · `on_llm_start` · `on_llm_end` · `on_tool_start` · `on_tool_end` · `on_agent_end` · `on_error`。这些值与 `BaseCallbackHandler` 方法名一一对应，Phase 1 即完整实现。
- **Phase 4 — SSE 协议层**（服务端推送事件类型，Phase 4 实现）：`thinking` · `tool_call` · `tool_result` · `final_answer` · `error` · `stream_token` · `memory_read` · `memory_write`。面向前端 UI 的语义化事件类型，Phase 4 将 Python 回调事件映射到此层并通过 SSE 推送。

两层体系**共用同一 `CallbackEvent` Envelope**（envelope schema 不变），Phase 4 的 SSE 适配器负责将 Python 回调层事件翻译为 SSE 语义层事件，不得修改 Python 层的方法名或 `CallbackEvent` 字段。

This format MUST NOT change between phases (additive fields are allowed; removals and renames are constitution amendments). Phase 4 MUST expose these events over **SSE (Server-Sent Events)** as the primary frontend streaming protocol. A synchronous REST endpoint MUST also be provided for non-streaming clients. WebSocket MAY be added for Human-in-the-Loop interactive sessions.

### VIII. 渐进式异步（Progressive Async Adoption）

- **Phase 1**: All agent code MUST be synchronous (`def`, not `async def`). This preserves readability for learning purposes.
- **Phase 2**: Streaming responses MUST use `async`/`await` with `asyncio`. The `ReactAgent` MUST gain an `async def run_stream()` method alongside the existing synchronous `run()`.
- **Phase 3+**: New I/O-bound components (vector store queries, memory retrieval) MUST be implemented as async. Synchronous wrappers MAY be provided for backward compatibility.
- Mixing sync and async in the same call stack (blocking the event loop) is a **blocking defect** from Phase 2 onward.

### IX. 自动重试与降级（Auto-Retry & Graceful Degradation）

Production agent systems MUST NOT crash on transient failures. The framework MUST enforce:

1. **LLM API calls**: Exponential back-off retry with jitter for `RateLimitError`, `APITimeoutError`, and `APIConnectionError`. Default: 3 retries, base delay 1 s, max delay 60 s. Jitter 公式：`delay = min(base × 2^attempt, max_delay) + uniform(0, jitter_factor × base)`，`jitter_factor` 默认 0.5，用于防止多 Agent 并发重试时的惊群效应（Thundering Herd）。**Phase 1 豁免**：Phase 1 MAY 通过在 LLMClient 初始化时配置 OpenAI SDK 的 `max_retries=3` 参数来满足本条（SDK 已内置指数退避，覆盖上述三种错误类型）；完整的自定义重试实现（含 Jitter 公式和错误分类，见 item 2）MUST 从 Phase 2 起引入。
2. **Error classification**: 重试前必须对错误分类，不同类型触发不同策略：
   - `rate_limit`（HTTP 429）→ 解析 `Retry-After` 响应头，按服务端建议退避
   - `context_overflow`（4xx context length）→ 触发上下文压缩后重试，不递增重试计数
   - `auth_error`（HTTP 401/403）→ 立即失败，不重试，上报告警
   - `network_error`（超时/连接断开）→ 标准指数退避重试
3. **Tool execution**: Each tool call MUST be wrapped in error handling; failures MUST return a `ToolResult(error=True)` observation to the agent loop — never propagate as an unhandled exception that terminates the run.
4. **Fallback chains**: LLMClient MUST support a `fallback_models` list; if the primary model fails after retries, the client MUST attempt the next model before raising.
5. **Circuit breaker**: Phase 4 MUST implement a circuit breaker for external service tools to prevent cascade failures.

Retry logic MUST be implemented in the LLM client layer and the tool registry layer — never duplicated in agent code.

### X. 核心模块测试覆盖（Mandatory Core Module Test Coverage）

Every core module MUST have a corresponding test file before the phase it is introduced is considered complete. Every core module across the following layers MUST have a corresponding test file: schema utilities、tool system、memory system（short-term and long-term）、LLM client and streaming handler、and all agent classes（single agent and orchestrator）.

Tests MUST cover the happy path and at least one error/edge case per public method. The LLM MUST be mocked in unit tests; integration tests MAY use real API calls but MUST be gated behind an environment variable (`RUN_INTEGRATION_TESTS=1`).

### XI. Human-in-the-Loop（人工介入机制）

Tools MUST declare an `is_destructive: bool` attribute. When `is_destructive=True`, the agent framework MUST pause execution before calling the tool and emit an `approval_required` event. Execution MUST NOT resume until an explicit `approve()` or `reject()` signal is received.

**强制要求**：`is_destructive=True` 的工具在未注册任何 HITL 处理器时，框架 MUST 抛出 `MissingHITLHandlerError` 异常，而非静默执行。开发模式可通过 `safe_mode=False` 显式绕过此检查，但 MUST 打印警告日志。

Phase 4 MUST implement state persistence so that a paused agent can survive process restarts: the full conversation state MUST be serializable to JSON and reloadable. 持久化游标设计：以 `thread_id`（`session_id + run_id` 的组合键）为唯一恢复凭证，只要 `thread_id` 不变，无论间隔多久均可从中断点精确恢复，无需重放历史步骤。This architecture — pause, persist, resume — MUST be designed from Phase 2 onward even if the full implementation ships in Phase 4.

### XII. 会话状态完全隔离（Complete Session State Isolation）

The framework core MUST contain **zero global mutable state**. Specifically:
- `ToolRegistry` instances MUST be per-agent, never shared across agents without explicit opt-in.
- `ConversationMemory` instances MUST be per-session.
- Class-level or module-level mutable variables are a **blocking defect**.
- When the Phase 4 server serves multiple concurrent users, each request MUST receive its own `ReactAgent` instance constructed fresh from a stateless factory.

The only permitted shared state is read-only: registered tool schemas, configuration constants, and the `LongTermMemory` store (which MUST be designed as a thread-safe / async-safe service).

### XIII. 上下文窗口主动管理（Proactive Context Window Management）

The framework MUST take responsibility for context length — this MUST NOT be delegated to users. `ConversationMemory` MUST support at least two strategies, selectable at construction time:

- **`sliding_window`** (default for Phase 1–3): Keep the N most recent messages; oldest non-system messages are dropped.
- **`summarize`** (Phase 3+): When the message history exceeds a configurable token threshold, automatically summarize older messages into a single summary message via an LLM call.

**截断保护规则（所有策略均适用）**：无论采用何种压缩策略，以下内容 MUST 始终保留，不得截断或摘要：
1. System Prompt（头部锚点，永远置于消息列表首位）
2. 所有 Tool Call / Tool Result 消息对（工具执行记录是 ReAct 循环的核心上下文）
3. 最近 N 轮完整对话（N 由 `keep_last_n` 参数控制，默认 6）
只有位于保护区之外的中间普通对话消息才可被截断或摘要。

**增量摘要策略（Phase 3+，`summarize` 模式下推荐）**：采用锚定迭代摘要（Anchored Iterative Summarization）——仅对新增的、超出阈值的部分进行增量摘要，追加到已有摘要尾部，而非重新生成全部历史的完整摘要。此策略在技术细节保留精度上显著优于全量摘要（实测准确率提升约 8%）。

Token counting MUST use the model's actual tokenizer (via `tiktoken` for OpenAI models) from Phase 3 onward; a character-count heuristic is acceptable for Phase 1–2.

### XIV. 结构化输入输出验证（Structured I/O Validation）

All data crossing module boundaries MUST be validated:

- **Tool arguments**: The tool registry's execution entry point MUST validate incoming arguments against the tool's Pydantic schema before dispatching to the tool implementation. Invalid arguments MUST return a structured error result with a descriptive message.
- **Agent output**: When a caller requests structured output (e.g., via `output_schema: type[BaseModel]`), the `ReactAgent` MUST parse and validate the final answer against that schema. Parse failures MUST trigger a retry with a correction prompt (max 2 retries).
- **LLM responses**: Malformed tool call JSON from the LLM MUST be caught and result in an `on_error` callback event, not an unhandled exception.

Raw `dict` passing between layers is prohibited where a typed `dataclass` or `BaseModel` can be used instead.

### XV. 安全边界（Security Boundaries）

**Prompt Injection Defense**: Tool results MUST be injected into the message history as `role: "tool"` messages, never interpolated directly into system or user prompt strings. The agent's system prompt MUST include an instruction that tool outputs are untrusted external data.

**Tool Permission Levels**: Every tool MUST declare one of:
- `permission: "read"` — safe to call without approval (default)
- `permission: "write"` — modifies state; triggers Human-in-the-Loop in production mode
- `permission: "destructive"` — irreversible; ALWAYS requires explicit human approval regardless of mode

**Production Mode Gate**: Phase 4 server MUST expose a `safe_mode: bool` configuration. When `True`, all `write` and `destructive` tools require approval. When `False` (development mode), tools run freely but a warning MUST be logged.

### XVI. 生态兼容性（Ecosystem Compatibility — MCP & Skills）

The tool registry MUST be extensible to support multiple tool sources without changing the agent loop:

- **MCP (Model Context Protocol)**: Phase 4 MUST ship an `MCPToolLoader` that connects to any MCP Server (stdio or HTTP transport) and registers its tools into a `ToolRegistry`. The agent treats MCP tools identically to local tools.
- **Skill Packages**: The framework MUST define a `Skill` format — a directory or importable package containing: one or more `BaseTool` subclasses, an optional system prompt fragment, and a `skill.json` manifest. Skills MUST be installable via `registry.load_skill("path/or/package")`.
- **Protocol Extensibility**: `ToolRegistry` MUST accept `ToolLoader` plugins so future protocols (A2A, custom REST tool APIs) can be added without modifying core code.
- **Multimodal Input**: Phase 4 or later MUST support non-text input types (images, audio, video) in both tool arguments and conversation messages. Concrete Phase 1 obligations:
  1. The `Message` data model's `content` field MUST be typed as `Union[str, list[ContentPart]]` from Phase 1, where `ContentPart` is a union of `TextContentPart`, `ImageContentPart`, and `AudioContentPart` (TypedDict + Literal discriminator pattern).
  2. `ToolResult`'s return value field MUST use the same `MessageContent = Union[str, list[ContentPart]]` type to allow tools to return images or audio in Phase 4.
  3. Phase 1's `LLMClient` MUST raise an explicit `NotImplementedError` when `content` is a `list[ContentPart]`, making the unsupported path fail fast and clearly.
  4. These type definitions MUST NOT change shape in later phases — Phase 4 only removes the `NotImplementedError` and adds serialization logic, breaking no existing callers.

### XVII. ReAct 循环终止规范（Loop Termination Contract）

ReAct 循环的终止逻辑 MUST 遵循以下优先级顺序，不得随意简化：

1. **主终止信号**：`finish_reason == "stop"` — LLM 认为任务已完成，框架立即返回最终答案。
2. **工具调用继续**：`finish_reason == "tool_calls"` — 执行工具后继续循环。
3. **安全兜底**：`max_iterations` 达到上限时，框架 MUST 向 LLM 发送一条追加消息："你已达到最大步骤数，请基于当前已有信息给出最终答案。"，再进行最后一次 LLM 调用后返回结果。**严禁直接截断循环并返回半成品答案。**

**实现模式**：MUST 使用枚举类型封装每步的循环走向，将四种状态（终止输出、继续循环、移交控制权、人工中断）显式建模为独立类型，取代字符串条件判断。四种状态类型的完整定义 MUST 在 Phase 1 建立，移交控制权和人工中断类型在 Phase 1 中可为占位实现，但类型定义不得缺失。

---

## Development Standards

### Phase Completion Gates

No phase MUST be declared complete unless ALL of the following pass:
1. All examples for that phase run without errors against a live OpenAI-compatible API.
2. All required test files for that phase exist and pass (`pytest tests/ -v`).
3. A Constitution Check (see plan-template.md) has been performed and all violations are documented with justification.

### Dependency Review Protocol

At the start of each phase, the dependency list in `pyproject.toml` MUST be audited. Any dependency not justified by Principle II MUST be removed before phase work begins.

### Async Migration Rules

When converting a synchronous function to async (Phase 2+), the synchronous version MUST be retained with a deprecation notice for one full phase before removal, unless it is internal-only.

### Documentation Standard

Each public class and function MUST have a one-line docstring stating its purpose. Multi-paragraph docstrings are prohibited. Inline comments MUST explain *why*, not *what*.

---

## Governance

This constitution supersedes all other written or verbal project conventions. In case of conflict between this document and any other guide, this document takes precedence.

**Amendment Procedure**:
1. Propose the amendment with: the principle affected, the change, and the rationale.
2. The amendment requires explicit acknowledgment from the project owner before taking effect.
3. Once approved, update this file, increment the version, update `LAST_AMENDED_DATE`, and run `/speckit-constitution` to propagate changes to dependent templates.
4. Breaking changes to existing principles (removals, redefinitions) require a MAJOR version bump.
5. New principles or material expansions require a MINOR version bump.
6. Clarifications and wording fixes require a PATCH version bump.

**Compliance Review**: Constitution Check MUST be performed at every phase boundary (see `plan-template.md`). Violations that are accepted must be recorded in the plan's Complexity Tracking table with justification.

**Version Policy**: Versions follow semantic versioning (`MAJOR.MINOR.PATCH`). The version on this file is the authoritative source; all templates reference "current constitution" implicitly.

**Version**: 1.3.1 | **Ratified**: 2026-05-07 | **Last Amended**: 2026-05-09
