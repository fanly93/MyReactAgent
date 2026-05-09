# Implementation Plan: Phase 1 MVP — ReAct Agent 核心框架

**Branch**: `001-phase1-mvp-prototype` | **Date**: 2026-05-08 | **Spec**: [spec.md](spec.md)  
**Input**: Feature specification from `specs/001-phase1-mvp-prototype/spec.md`

---

## Summary

实现一个从零开始的 ReAct Agent 框架 Phase 1：支持同步工具调用（装饰器 + 类继承两种定义方式）、多轮对话（滑动窗口上下文管理）、同步流式输出（`Iterator[str]`）、7 类生命周期回调、Pydantic 参数验证、完整的会话隔离，仅依赖 `openai` SDK 和 `pydantic` v2，全部代码同步执行。完成标志：`examples/01_basic_tool_use.py` 端到端运行成功。

---

## Technical Context

**Language/Version**: Python 3.11+  
**Primary Dependencies**: `openai` SDK（LLM 调用，含 `max_retries=3` 指数退避）、`pydantic` v2（数据验证 + JSON Schema 生成）  
**Storage**: 纯内存（`list[Message]`），会话结束后不保留，无持久化（Phase 3 引入）  
**Testing**: `pytest` + `pytest-mock`；单元测试无需真实 API（LLM 通过 mock 测试）；集成测试通过 `RUN_INTEGRATION_TESTS=1` 门控  
**Target Platform**: Linux/macOS，Python 3.11+ 开发/服务器环境  
**Project Type**: library（Python 包，开发者直接 `import` 使用）  
**Performance Goals**: Phase 1 可读性优先，无量化性能目标；能在笔记本开发环境流畅运行即可  
**Constraints**: 仅支持同步执行（含同步流式迭代器，无 `async/await`）；禁止引入任何 Agent 框架库  
**Scale/Scope**: 单 Agent 单会话，支持开发者本地运行和测试

---

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

- [x] **I. Readability** — Phase 1 采用显式循环、无复杂抽象，代码结构清晰，适合学习 ReAct 内部机制；无过早优化。
- [x] **II. Dependencies** — 仅 `openai`（LLM 调用必要）和 `pydantic`（替代 200+ 行验证代码）；无便利性依赖；`pytest-mock` 仅在测试中使用。
- [x] **III. Explicit** — 工具注册通过 `registry.register()` 或 `@tool` 装饰器显式进行；配置通过构造参数传入；错误作为 typed 结果（`ToolResult`）或 typed exception 返回，不静默吞掉。
- [x] **IV. Layer Boundaries** — 设计遵循 `schemas/ → tools/ → llm/ + memory/ → callbacks/ → agent/` 层次（`schemas/` 作为共享类型层），无跨层依赖，无上行导入。
- [x] **V. Phase Gate** — 这是 Phase 1 首个功能；前置阶段（项目初始化）已完成（git 仓库存在、CLAUDE.md 建立、宪法确立）。
- [x] **VI. Observability** — 所有 7 类生命周期事件通过 `BaseCallbackHandler` 接口发出；`ReactAgent._emit()` 是唯一触发点；核心循环代码中无 `print()` 散布。
- [x] **VII. Event Format** — `CallbackEvent` 包含 6 个字段：`event`、`data`、`timestamp`（ISO-8601）、`session_id`、`run_id`、`span_id`（Phase 1 留空字符串）；Schema 不随阶段变更。
- [x] **VIII. Async Rules** — Phase 1 全同步；`run_stream()` 返回同步迭代器（`Iterator[str]`），不含 `async/await`；Phase 2 才引入 `async def run_stream()`。
- [x] **IX. Retry/Fallback** — `LLMClient` 初始化时配置 `max_retries=3`，委托 SDK 对 `RateLimitError`/`APIConnectionError`/`APITimeoutError` 执行指数退避（Phase 1 豁免条款适用）；工具异常被捕获并转化为 `ToolResult(success=False)`。
- [x] **X. Tests** — 计划为每个核心模块创建对应单元测试文件：`test_schemas.py`、`test_tools.py`、`test_registry.py`、`test_memory.py`、`test_llm_client.py`、`test_callbacks.py`、`test_agent.py`。
- [x] **XI. HITL** — `BaseTool` 声明 `is_destructive: bool` 和 `permission: Literal[...]` 属性；Phase 1 不实现门控逻辑，但属性 schema 完整，确保 Phase 4 在不修改调用方代码的前提下激活。
- [x] **XII. Session Isolation** — 无全局可变状态；`ConversationMemory` 和 `ToolRegistry` 均为实例变量，非类变量；两个 Agent 实例的历史完全隔离。
- [x] **XIII. Context Management** — `ConversationMemory` 内置滑动窗口策略：`max_messages=20`（默认）、`keep_last_n=6`（轮，默认）；保护 system prompt、tool call pairs（原子单元）和最近 N 轮完整对话。
- [x] **XIV. Validation** — 工具参数在执行前通过对应 Pydantic 模型验证（`ToolRegistry.execute()` 入口统一处理）；LLM 返回的 tool call JSON 解析失败时触发 `on_error` 并作为 tool 结果返回。
- [x] **XV. Security** — 工具结果作为 `role="tool"` 消息注入历史（非字符串插值）；系统提示包含工具输出为不可信外部数据的说明；工具声明 `permission: Literal["read", "write", "destructive"]`。
- [x] **XVI. Ecosystem** — `Message.content` 从 Phase 1 起定义为 `Union[str, list[ContentPart]]`，含 `TextContentPart`/`ImageContentPart`/`AudioContentPart`；Phase 1 遇到 `list[ContentPart]` 时抛出明确 `NotImplementedError`；`ToolResult.content` 同步预留。
- [x] **XVII. Loop Termination** — `NextStep` 枚举含 4 种状态（`STOP`/`CONTINUE`/`HANDOFF`/`INTERRUPT`）；`STOP` 和 `CONTINUE` Phase 1 完整实现；安全兜底：`max_iterations` 达上限时追加消息后再进行最后一次 LLM 调用，禁止直接截断返回。

**Constitution Check Result**: ✅ 全部通过，无违规项，无需 Complexity Tracking 记录。

---

## Project Structure

### Documentation (this feature)

```text
specs/001-phase1-mvp-prototype/
├── spec.md           # 功能规范
├── plan.md           # 本文件（/speckit-plan 输出）
├── research.md       # Phase 0 研究报告（/speckit-plan 输出）
├── data-model.md     # 数据模型（/speckit-plan 输出）
├── quickstart.md     # 快速开始指南（/speckit-plan 输出）
├── contracts/
│   └── public-api.md # 公共 API 契约（/speckit-plan 输出）
└── tasks.md          # 任务分解（/speckit-tasks 输出，尚未生成）
```

### Source Code (repository root)

```text
myreactagent/
├── __init__.py                   # 公共导出：ReactAgent, tool, BaseTool, ToolResult
├── schemas/
│   ├── __init__.py
│   ├── messages.py               # Message, ContentPart, ToolCall, MessageContent
│   ├── events.py                 # CallbackEvent, NextStep
│   └── tools.py                  # ToolResult
├── tools/
│   ├── __init__.py
│   ├── base.py                   # BaseTool ABC
│   ├── decorator.py              # @tool 装饰器（从函数签名生成 Schema）
│   └── registry.py               # ToolRegistry（注册、验证、执行入口）
├── llm/
│   ├── __init__.py
│   └── client.py                 # LLMClient（OpenAI SDK 封装，max_retries=3）
├── memory/
│   ├── __init__.py
│   └── conversation.py           # ConversationMemory（滑动窗口截断）
├── callbacks/
│   ├── __init__.py
│   ├── base.py                   # BaseCallbackHandler ABC（7 个默认空实现方法）
│   └── console.py                # ConsoleCallbackHandler（开箱即用控制台输出）
└── agent/
    ├── __init__.py
    └── react.py                  # ReactAgent（ReAct 循环、_emit 分发、run/run_stream）

tests/
├── __init__.py
├── unit/
│   ├── __init__.py
│   ├── test_schemas.py           # Message, ContentPart, ToolResult, CallbackEvent 验证
│   ├── test_tools.py             # BaseTool, @tool 装饰器, Schema 生成
│   ├── test_registry.py          # ToolRegistry 注册、参数验证、执行、错误捕获
│   ├── test_memory.py            # ConversationMemory 截断算法、边界条件
│   ├── test_llm_client.py        # LLMClient（mock openai 客户端）
│   ├── test_callbacks.py         # BaseCallbackHandler, ConsoleCallbackHandler
│   └── test_agent.py             # ReactAgent 循环逻辑（mock LLMClient）
└── integration/
    ├── __init__.py
    └── test_e2e.py               # 端到端集成测试（RUN_INTEGRATION_TESTS=1 门控）

examples/
└── 01_basic_tool_use.py          # Phase 1 完成标志示例

pyproject.toml                    # 依赖：openai, pydantic≥2.0；dev: pytest, pytest-mock
```

**Structure Decision**: 单项目结构（Option 1），包名 `myreactagent`，直接位于仓库根目录。`schemas/` 作为跨层共享的纯数据类型层，替代空的 `utils/`（Phase 1 无通用工具函数）。遵循宪法 IV 层次边界：`schemas/ → tools/ → llm/ + memory/ → callbacks/ → agent/`。

---

## Complexity Tracking

> Phase 1 接受的宪法豁免项如下：

| 违规 | 必要性 | 替代方案放弃原因 |
|------|--------|-----------------|
| 宪法 XI：`is_destructive=True` 时未暂停执行、未抛出 `MissingHITLHandlerError` | Phase 1 不实现 HITL；宪法原文注明 "This architecture MUST be designed from **Phase 2** onward"，Phase 1 明确豁免 | Phase 4 完整实现；Phase 1 已在 `BaseTool` 完整声明 `is_destructive`/`permission` 属性 schema，Phase 4 可在不修改调用方代码的前提下激活门控逻辑 |

---

## Implementation Notes

### ReAct 循环伪代码

```
def run(user_message: str) -> str:
    run_id = uuid4()
    memory.add(Message(role="user", content=user_message))
    emit(on_agent_start, {user_message, system_prompt})

    for iteration in range(max_iterations):
        messages = memory.get_messages()
        emit(on_llm_start, {messages, tools_schema, stream=False})
        response = llm.chat(messages, tools_schema)
        emit(on_llm_end, {content, tool_calls, finish_reason})

        next_step = decide_next_step(response)  # → NextStep 枚举

        if next_step == NextStep.STOP:
            memory.add(Message(role="assistant", content=response.content))
            emit(on_agent_end, {final_answer, iterations})
            return response.content

        if next_step == NextStep.CONTINUE:
            memory.add(assistant_message_with_tool_calls)
            for tool_call in response.tool_calls:
                emit(on_tool_start, {tool_name, tool_call_id, args})
                result = registry.execute(tool_call.function.name, parsed_args)
                emit(on_tool_end, {tool_name, tool_call_id, success, result})
                memory.add(result.to_message())

    # 安全兜底（宪法 XVII）
    memory.add(Message(role="user", content="你已达到最大步骤数，请基于当前已有信息给出最终答案。"))
    emit(on_llm_start, ...)
    final_response = llm.chat(memory.get_messages(), tools_schema)
    emit(on_llm_end, ...)
    emit(on_agent_end, ...)
    return final_response.content
```

### 关键实现约束

1. **工具调用配对消息原子性**：`ConversationMemory._truncate()` 中，`role=assistant`（含 `tool_calls`）和紧随其后的所有 `role=tool` 消息作为原子单元，不得被截断拆开（否则 OpenAI API 报错）。

2. **流式 tool_calls 重建**：`run_stream()` 中，LLM 流式响应里 `tool_calls` 以增量 delta 形式到来，需按 `index` 累积（`id`、`name` 只在第一个 delta 出现，`arguments` 需字符串拼接），流结束后重建完整 `tool_calls` 列表。

3. **同步流式的 yield 范围**：`run_stream()` 只 yield 最终答案阶段的 token；工具调用执行阶段（`finish_reason="tool_calls"`）在后台同步执行，不 yield。

4. **`@tool` 装饰器 Schema 生成**：使用 `typing.get_type_hints(func)` 解析参数类型，`pydantic.create_model()` 动态建模，`model.model_json_schema()` 生成 JSON Schema，过滤 `return` 键，无类型注解参数默认 `str`。

5. **`LLMClient.chat()` 接口统一**：非流式和流式通过 `stream: bool` 参数区分，内部路由到两条代码路径；`ReactAgent` 在 `run()` 中始终调用非流式（需要完整 response 判断 `finish_reason`）；`run_stream()` 在最终答案阶段调用流式。

### 依赖安装

```toml
# pyproject.toml
[project]
name = "myreactagent"
requires-python = ">=3.11"
dependencies = [
    "openai>=1.0.0",
    "pydantic>=2.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-mock>=3.0",
]
```
