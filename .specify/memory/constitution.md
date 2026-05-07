<!--
同步影响报告
============
版本变更：（无 / 模板） → 1.0.0（首次正式批准）
版本说明：首个完整宪法，全部 16 条原则从零起草。

新增章节：
  - 核心原则（I – XVI，共 16 条）
  - 开发规范
  - 治理机制

修改原则：无（首版）
删除章节：所有模板占位注释

已更新模板：
  ✅ .specify/memory/constitution.md         — 本文件
  ✅ .specify/templates/plan-template.md     — 宪法检查项更新为 16 条具体门控
  ✅ .specify/templates/spec-template.md     — 无需修改，结构兼容
  ✅ .specify/templates/tasks-template.md    — 无需修改，结构兼容

待办事项：无，所有占位符已填写完毕。
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

`on_agent_start` · `on_llm_call` · `on_llm_response` · `on_tool_call` · `on_tool_result` · `on_agent_finish` · `on_error`

Core agent code MUST only call `self._emit(event_type, payload)` at these points — one call per event, no business logic inside the emit path. All logging, tracing, metrics, and LangSmith-style instrumentation MUST be implemented as `BaseCallbackHandler` subclasses, never in the agent loop itself. Phase 1 MUST ship a `ConsoleCallbackHandler` as the default; Phase 4 MUST add an `OpenTelemetryCallbackHandler`.

### VII. 统一事件格式与前端集成（Unified Event Format & Frontend Integration）

All agent runtime events MUST conform to a single JSON envelope from Phase 1 onward:

```json
{"event": "<type>", "data": {…}, "timestamp": "<ISO-8601>", "session_id": "<uuid>"}
```

Valid `event` types: `thinking` · `tool_call` · `tool_result` · `final_answer` · `error` · `stream_token`

This format MUST NOT change between phases (additive fields are allowed; removals and renames are constitution amendments). Phase 4 MUST expose these events over **SSE (Server-Sent Events)** as the primary frontend streaming protocol. A synchronous REST endpoint MUST also be provided for non-streaming clients. WebSocket MAY be added for Human-in-the-Loop interactive sessions.

### VIII. 渐进式异步（Progressive Async Adoption）

- **Phase 1**: All agent code MUST be synchronous (`def`, not `async def`). This preserves readability for learning purposes.
- **Phase 2**: Streaming responses MUST use `async`/`await` with `asyncio`. The `ReactAgent` MUST gain an `async def run_stream()` method alongside the existing synchronous `run()`.
- **Phase 3+**: New I/O-bound components (vector store queries, memory retrieval) MUST be implemented as async. Synchronous wrappers MAY be provided for backward compatibility.
- Mixing sync and async in the same call stack (blocking the event loop) is a **blocking defect** from Phase 2 onward.

### IX. 自动重试与降级（Auto-Retry & Graceful Degradation）

Production agent systems MUST NOT crash on transient failures. The framework MUST enforce:

1. **LLM API calls**: Exponential back-off retry with jitter for `RateLimitError`, `APITimeoutError`, and `APIConnectionError`. Default: 3 retries, base delay 1 s, max delay 60 s.
2. **Tool execution**: Each tool call MUST be wrapped in error handling; failures MUST return a `ToolResult(error=True)` observation to the agent loop — never propagate as an unhandled exception that terminates the run.
3. **Fallback chains**: LLMClient MUST support a `fallback_models` list; if the primary model fails after retries, the client MUST attempt the next model before raising.
4. **Circuit breaker**: Phase 4 MUST implement a circuit breaker for external service tools to prevent cascade failures.

Retry logic MUST be implemented in `llm/client.py` and `tools/registry.py` — never duplicated in agent code.

### X. 核心模块测试覆盖（Mandatory Core Module Test Coverage）

Every core module MUST have a corresponding test file before the phase it is introduced is considered complete. The following modules are non-negotiable:

| Module | Required Test File |
|--------|-------------------|
| `utils/schema.py` | `tests/test_schema.py` |
| `tools/` | `tests/test_tools.py` |
| `memory/short_term.py` | `tests/test_memory.py` |
| `memory/vector_store.py` | `tests/test_memory.py` |
| `llm/client.py` | `tests/test_llm_client.py` |
| `llm/streaming.py` | `tests/test_streaming.py` |
| `agent/react_agent.py` | `tests/test_react_loop.py` |
| `agent/orchestrator.py` | `tests/test_orchestrator.py` |

Tests MUST cover the happy path and at least one error/edge case per public method. The LLM MUST be mocked in unit tests; integration tests MAY use real API calls but MUST be gated behind an environment variable (`RUN_INTEGRATION_TESTS=1`).

### XI. Human-in-the-Loop（人工介入机制）

Tools MUST declare an `is_destructive: bool` attribute. When `is_destructive=True`, the agent framework MUST pause execution before calling the tool and emit an `approval_required` event. Execution MUST NOT resume until an explicit `approve()` or `reject()` signal is received.

Phase 4 MUST implement state persistence so that a paused agent can survive process restarts: the full conversation state MUST be serializable to JSON and reloadable. This architecture — pause, persist, resume — MUST be designed from Phase 2 onward even if the full implementation ships in Phase 4.

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

Token counting MUST use the model's actual tokenizer (via `tiktoken` for OpenAI models) from Phase 3 onward; a character-count heuristic is acceptable for Phase 1–2.

### XIV. 结构化输入输出验证（Structured I/O Validation）

All data crossing module boundaries MUST be validated:

- **Tool arguments**: The `ToolRegistry.execute()` method MUST validate incoming `kwargs` against the tool's Pydantic schema before calling `tool.run()`. Invalid arguments MUST return a `ToolResult(error=True)` with a descriptive message.
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

**Version**: 1.0.0 | **Ratified**: 2026-05-07 | **Last Amended**: 2026-05-07
