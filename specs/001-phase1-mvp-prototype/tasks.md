# Tasks: Phase 1 MVP — ReAct Agent 核心框架

**Input**: `specs/001-phase1-mvp-prototype/` (spec.md + plan.md + data-model.md + contracts/)  
**Branch**: `001-phase1-mvp-prototype`  
**生成时间**: 2026-05-08  
**完成标志**: `examples/01_basic_tool_use.py` 端到端运行成功

---

## 格式说明

```
- [X] T001 [P0] 描述 → 文件路径
       [P]   = 可并行（不同文件，无未完成依赖）
       [USn] = 对应用户故事（US1–US4）
       [P0]  = 必须（阻塞后续）/ [P1] = 应该实现 / [P2] = 可选改善
       depends: T-X,T-Y = 依赖关系
       est: NNN min = 预计工时
```

---

## Phase 1: Setup — 项目初始化

**目的**: 建立项目骨架，为所有后续开发奠基  
**阻塞条件**: 无前置依赖，可立即开始

- [X] T001 [P0] 初始化 `pyproject.toml`：声明 `openai>=1.0` + `pydantic>=2.0` 运行依赖，`pytest>=7.0` + `pytest-mock>=3.0` 开发依赖，`requires-python=">=3.11"` → `pyproject.toml`  
  *est: 15 min*

- [X] T002 [P0] 创建完整目录骨架：`myreactagent/{schemas,tools,llm,memory,callbacks,agent}/`、`tests/{unit,integration}/`、`examples/`，每个目录写入空 `__init__.py` → `myreactagent/**/__init__.py`、`tests/**/__init__.py`  
  *depends: T001 | est: 10 min*

**✅ Checkpoint**: `python -m pytest tests/` 可执行（0 tests collected）

---

## Phase 2: Foundational — 核心数据类型（阻塞所有用户故事）

**目的**: 定义跨层共享的 Pydantic 数据模型；所有上层模块均依赖此层  
**⚠️ CRITICAL**: 本阶段全部完成前，任何用户故事均不得开始

- [X] T003 [P0] 实现消息数据模型：`TextContentPart`、`ImageContentPart`（Phase 1 预留）、`AudioContentPart`（Phase 1 预留）、`ContentPart` Union、`MessageContent = Union[str, list[ContentPart]]`、`ToolCallFunction`、`ToolCall`、`Message`（含 `to_openai_dict()` 方法，`list[ContentPart]` 分支抛 `NotImplementedError`）→ `myreactagent/schemas/messages.py`  
  *depends: T002 | est: 35 min*

- [X] T004 [P0] [P] 实现事件与循环控制类型：`CallbackEvent`（6 字段：event/data/timestamp/session_id/run_id/span_id）、`NextStep` 枚举（STOP/CONTINUE/HANDOFF/INTERRUPT，后两者 Phase 1 为占位）→ `myreactagent/schemas/events.py`  
  *depends: T002 | est: 20 min*

- [X] T005 [P0] 实现工具结果类型：`ToolResult`（tool_call_id/success/content/error/error_type/error_message，含 `to_message() → Message` 方法）→ `myreactagent/schemas/tools.py`  
  *depends: T002, T003 | est: 15 min*

- [X] T006 [P0] 填写公共导出：`myreactagent/schemas/__init__.py` 导出所有 schema 类型；`myreactagent/__init__.py` 预留顶层导出占位（后续阶段填充）→ `myreactagent/schemas/__init__.py`、`myreactagent/__init__.py`  
  *depends: T003,T004,T005 | est: 10 min*

- [X] T007 [P0] 编写 schemas 单元测试：覆盖 `Message.to_openai_dict()` 各 role 分支、`list[ContentPart]` 抛 `NotImplementedError`、`ToolResult.to_message()` 成功/失败分支、`NextStep` 枚举值、`CallbackEvent` 字段校验 → `tests/unit/test_schemas.py`  
  *depends: T006 | est: 30 min*

**✅ Checkpoint**: `pytest tests/unit/test_schemas.py -v` 全部通过

---

## Phase 3: User Story 1 — 单次多步骤任务执行（Priority: P1 → 实现为 P0）

**目标**: 框架核心价值主张——定义工具、创建 Agent、自主完成多步骤 ReAct 循环

**独立验收测试**: 定义算术工具，向 Agent 提问"3 乘以 7 加上 8 等于多少"，Agent 在 ≤5 轮内给出正确答案 29，无需人工干预

### 工具系统

- [X] T008 [P0] [US1] 实现 `BaseTool` 抽象基类：抽象属性 `name`/`description`/`parameters_schema`，类属性 `is_destructive: bool = False`/`permission: Literal["read","write","destructive"] = "read"`，抽象方法 `execute(args: dict) → ToolResult` → `myreactagent/tools/base.py`  
  *depends: T005,T006 | est: 20 min*

- [X] T009 [P0] [P] [US1] 实现 `@tool` 装饰器：通过 `inspect.signature()` + `typing.get_type_hints()` 提取参数，`pydantic.create_model()` 动态建模，`model.model_json_schema()` 生成 JSON Schema，无类型注解参数默认 `str`，支持 `@tool(is_destructive=True, permission="destructive")` 参数化形式 → `myreactagent/tools/decorator.py`  
  *depends: T008 | est: 40 min*

- [X] T010 [P0] [P] [US1] 实现 `ToolRegistry`：实例变量 `_tools: dict[str, BaseTool]`（非类变量），`register(tool)`、`get_tool(name)`、`get_openai_schemas() → list[dict]`（OpenAI function calling 格式）、`execute(name, args_dict) → ToolResult`（Pydantic 验证后分发，捕获 `ValidationError` 和 `Exception` 转化为 `ToolResult(success=False)`）→ `myreactagent/tools/registry.py`  
  *depends: T008 | est: 35 min*

- [X] T011 [P0] [P] [US1] 编写工具装饰器单元测试：覆盖有/无类型注解的函数生成正确 Schema、文档字符串提取、`is_destructive`/`permission` 默认值与覆盖、装饰器包装后 `execute()` 正常调用 → `tests/unit/test_tools.py`  
  *depends: T009 | est: 35 min*

- [X] T012 [P0] [P] [US1] 编写 `ToolRegistry` 单元测试：覆盖注册与查找、`get_openai_schemas()` 输出格式、Pydantic 验证失败返回结构化错误、工具执行异常被捕获、多工具调用顺序执行 → `tests/unit/test_registry.py`  
  *depends: T010 | est: 30 min*

### LLM 客户端（非流式）

- [X] T013 [P0] [P] [US1] 实现 `LLMClient` 非流式部分：构造时传入 `model`/`base_url`/`api_key`，`openai.OpenAI(max_retries=3)` 初始化，`chat(messages: list[dict], tools: list[dict] | None) → ChatCompletion` 方法（仅非流式，无 `stream` 参数），从环境变量 `OPENAI_MODEL`/`OPENAI_BASE_URL`/`OPENAI_API_KEY` 读取默认值，显式传参优先于环境变量 → `myreactagent/llm/client.py`  
  *depends: T003,T004,T006 | est: 30 min*

- [X] T014 [P0] [P] [US1] 编写 `LLMClient` 非流式单元测试：mock `openai.OpenAI`，覆盖正常响应解析、`finish_reason="stop"` 与 `"tool_calls"` 两路径、`max_retries=3` 配置验证 → `tests/unit/test_llm_client.py`  
  *depends: T013 | est: 25 min*

### 回调基础接口（Agent 依赖）

- [X] T015 [P0] [P] [US1] 实现 `BaseCallbackHandler` ABC：7 个方法（`on_agent_start`/`on_llm_start`/`on_llm_end`/`on_tool_start`/`on_tool_end`/`on_agent_end`/`on_error`）均为接受 `CallbackEvent` 参数的默认空实现（`pass`），子类按需覆盖 → `myreactagent/callbacks/base.py`  
  *depends: T004,T006 | est: 15 min*

### 基础对话记忆（Agent 依赖）

- [X] T016 [P0] [P] [US1] 实现 `ConversationMemory` 基础版（不含截断）：构造接受 `max_messages: int = 20`/`keep_last_n: int = 6`，实例变量 `_messages: list[Message]`，`add(message: Message)`、`get_messages() → list[Message]`、`clear()` 方法（截断逻辑在 T019 实现） → `myreactagent/memory/conversation.py`  
  *depends: T003,T006 | est: 20 min*

### Agent 核心 ReAct 循环

- [X] T017 [P0] [US1] 实现 `ReactAgent.run()` 完整 ReAct 循环：构造函数接受全部参数（tools/system_prompt/session_id/max_iterations/max_messages/keep_last_n/callbacks/model/base_url/api_key），自动生成 UUID session_id，内部创建 `ConversationMemory`/`ToolRegistry`/`LLMClient` 实例，`_emit(event)` 遍历 callbacks 分发，`run()` 实现含：`on_agent_start`→LLM循环→`NextStep` 判断→工具执行（每个工具触发 `on_tool_start`/`on_tool_end`）→`on_agent_end`，`max_iterations` 安全兜底（追加消息后再调一次 LLM），tool call JSON 解析失败触发 `on_error`；`_emit(event)` 内对每个 callback 调用包裹独立的 `try/except Exception`，确保单个回调抛出异常时不中断主循环 → `myreactagent/agent/react.py`  
  *depends: T010,T013,T015,T016 | est: 90 min*

- [X] T018 [P0] [US1] 编写 `ReactAgent` 单元测试：mock `LLMClient`，覆盖单次 STOP 循环、一次工具调用后 STOP、多工具同一轮调用、工具执行失败后循环继续、`max_iterations` 安全兜底触发、空工具列表纯对话模式 → `tests/unit/test_agent.py`  
  *depends: T017 | est: 50 min*

**✅ Checkpoint**: `pytest tests/unit/ -v` 全部通过；可手动验证算术工具示例运行

---

## Phase 4: User Story 2 — 多轮对话上下文保持（Priority: P2 → 实现为 P1）

**目标**: 同一会话内保留历史、自动截断、完全隔离

**独立验收测试**: 第一轮告知名字，第二轮直接询问，Agent 能正确回答；两个独立 Agent 实例的历史完全不交叉

### 滑动窗口截断

- [X] T019 [P1] [US2] 实现 `ConversationMemory._truncate()` 滑动窗口算法：三类保护区（`system` 消息永远保留、`assistant+tool` 配对原子保护、最近 `keep_last_n` 轮完整对话），仅截断保护区外中间普通消息，超出 `max_messages` 时逐条移除最旧非保护消息，无法继续截断时记录警告 → `myreactagent/memory/conversation.py`（在 `add()` 后调用）  
  *depends: T016 | est: 50 min*

- [X] T020 [P1] [P] [US2] 编写 `ConversationMemory` 截断算法单元测试：覆盖正常截断、system 消息不被删除、tool_call 配对消息原子保护不拆开、`keep_last_n` 轮保护、截断后消息数 ≤ `max_messages`、超出保护区无法截断时的边界情况 → `tests/unit/test_memory.py`  
  *depends: T019 | est: 45 min*

- [X] T021 [P1] [P] [US2] 在 `test_agent.py` 追加会话隔离测试：验证两个并发 `ReactAgent` 实例各自历史完全独立，一个实例的消息不出现在另一个实例的 `get_messages()` 中，验证无全局可变状态 → `tests/unit/test_agent.py`  
  *depends: T018,T019 | est: 20 min*

**✅ Checkpoint**: 对话历史 >20 条时自动截断；两个 Agent 实例互不干扰

---

## Phase 5: User Story 3 — 实时流式输出（Priority: P3 → 实现为 P1）

**目标**: `run_stream()` 返回同步迭代器，最终答案阶段逐 token yield，工具执行阶段后台运行

**独立验收测试**: 向 Agent 提交多步推理问题，终端逐词实时打印，截断流时已输出内容为完整片段

### LLM 流式接口

- [X] T022 [P0] [P] [US3] 在 `LLMClient` 追加流式方法：`chat_stream(messages, tools) → Iterator[ChatCompletionChunk]`，原样透传 SDK `Stream` 的同步 chunks，不做任何 tool_calls 重建或拼接；tool_calls 的增量累积与重建逻辑由调用方（`ReactAgent.run_stream()`）负责 → `myreactagent/llm/client.py`  
  *depends: T013 | est: 35 min*

- [X] T023 [P0] [US3] 在 `ReactAgent` 实现 `run_stream()` 方法：消费 `LLMClient.chat_stream()` 返回的原始 chunks，在方法内部按 `index` 累积重建完整 tool_calls（`id`/`name` 取首个 delta，`arguments` 字符串拼接）；`finish_reason="tool_calls"` 时后台同步执行工具（不 yield）；`finish_reason="stop"` 时逐 token yield 文字片段；`on_llm_end` 在流结束内容拼接完毕后触发，携带完整内容；重用 `run()` 的工具执行和 callback 分发逻辑 → `myreactagent/agent/react.py`  
  *depends: T017,T022 | est: 50 min*

- [X] T024 [P0] [P] [US3] 追加流式单元测试：在 `test_llm_client.py` 覆盖 tool_calls 增量累积与重建正确性；在 `test_agent.py` 覆盖 `run_stream()` yield token 序列、工具调用后 yield 继续、`on_llm_end` 携带完整内容 → `tests/unit/test_llm_client.py`、`tests/unit/test_agent.py`  
  *depends: T023 | est: 30 min*

**✅ Checkpoint**: `for token in agent.run_stream("...")` 可逐词打印

---

## Phase 6: User Story 4 — 执行过程可观测（Priority: P3 → 实现为 P1）

**目标**: 内置 `ConsoleCallbackHandler`，7 类事件按序触发，无回调时零性能损耗

**独立验收测试**: 注册 `ConsoleCallbackHandler`，运行含工具调用的 Agent，控制台依次打印 `on_agent_start → on_llm_start → on_llm_end → on_tool_start → on_tool_end → on_llm_start → on_llm_end → on_agent_end`

- [X] T025 [P0] [US4] 实现 `ConsoleCallbackHandler`：覆盖 7 个方法，每个方法打印格式化事件信息（时间戳 + 事件类型 + 关键 data 字段），`on_error` 额外打印错误类型和消息 → `myreactagent/callbacks/console.py`  
  *depends: T015 | est: 25 min*

- [X] T026 [P0] [P] [US4] 编写回调单元测试：覆盖 `BaseCallbackHandler` 空实现不报错、`ConsoleCallbackHandler` 各方法输出包含预期字段（使用 `capsys`）、回调方法抛出异常时 `_emit()` 不中断主循环（框架内部 try/except 保护）→ `tests/unit/test_callbacks.py`  
  *depends: T025 | est: 25 min*

- [X] T027 [P0] [US4] 验证并补全 `agent/react.py` 中所有 7 类 `_emit()` 调用点：确认 `on_error` 仅在 tool call JSON 解析失败等框架层错误路径触发（工具执行异常由 `on_tool_end(success=False)` 处理，不触发 `on_error`，符合 FR-013），`on_tool_start`/`on_tool_end` 在每个 tool_call 独立触发（非仅整组），`run_stream()` 中 `on_llm_start`/`on_llm_end` 与 `run()` 对称 → `myreactagent/agent/react.py`  
  *depends: T017,T025 | est: 25 min*

**✅ Checkpoint**: `pytest tests/unit/test_callbacks.py -v` 通过；控制台可见 8 步事件序列

---

## Phase 7: Polish & Integration — 收尾与端到端验证

**目的**: Phase 1 完成门控验证，端到端集成测试，公共 API 收拢

- [X] T028 [P0] 实现 Phase 1 完成标志示例：展示装饰器工具、类继承工具（共 ≥3 种工具）、多轮对话（≥2 轮）、流式输出、`ConsoleCallbackHandler` 的完整使用流程，文件可直接 `python examples/01_basic_tool_use.py` 运行成功 → `examples/01_basic_tool_use.py`  
  *depends: T017,T023,T025 | est: 35 min*

- [X] T029 [P1] 实现端到端集成测试：测试函数加 `@pytest.mark.integration` + `RUN_INTEGRATION_TESTS=1` 环境变量门控，覆盖：算术工具多步骤调用给出正确答案（SC-001/SC-002）、工具异常不崩溃继续循环（SC-003）、10 个并发会话历史无交叉（SC-004）、7 类事件完整触发（SC-005）→ `tests/integration/test_e2e.py`  
  *depends: T028 | est: 35 min*

- [X] T030 [P2] 收拢公共导出与包文档：更新 `myreactagent/__init__.py` 导出 `ReactAgent`/`BaseTool`/`tool`/`ToolResult`/`BaseCallbackHandler`/`ConsoleCallbackHandler`，为每个公共类和函数补全一行 docstring，验证 `from myreactagent import ReactAgent` 可直接使用 → `myreactagent/__init__.py`、各模块 `__init__.py`  
  *depends: T029 | est: 15 min*

- [X] T031 [P0] [补录] 实现工具输出截断（FR-006b）：`ToolRegistry.execute()` 内将工具输出超过 `MAX_TOOL_OUTPUT_CHARS=8000` 字符时截断并追加 `...[truncated]` 标记，防止单次工具输出撑满 LLM 上下文 → `myreactagent/tools/registry.py`  
  *depends: T010 | est: 10 min*

- [X] T032 [P0] [补录] 实现原子对溢出 on_error warning（FR-007b）：`ConversationMemory.add()` 引入 `_last_add_overflowed: bool` 标志，assistant+tool 原子对消息数超出 `max_messages` 时置位；`ReactAgent.run()` 和 `run_stream()` 在添加完一轮工具消息后检测标志，溢出时触发 `on_error(warning=True, error_type="ContextOverflow")` → `myreactagent/memory/conversation.py`、`myreactagent/agent/react.py`  
  *depends: T017, T019 | est: 20 min*

**✅ Phase 1 完成门控**: `python examples/01_basic_tool_use.py` 成功 + `pytest tests/unit/ -v` 100% 通过

---

## 依赖关系与执行顺序

### 阶段依赖链

```
Phase 1 (Setup)
    └─▶ Phase 2 (Schemas) ── 阻塞所有用户故事
            └─▶ Phase 3 (US1) ── P0 必须，阻塞 Phase 7
                    ├─▶ Phase 4 (US2)  ─┐
                    ├─▶ Phase 5 (US3)  ─┼─▶ Phase 7 (Polish)
                    └─▶ Phase 6 (US4)  ─┘
```

### 任务级依赖速查

| 任务 | 依赖 |
|------|------|
| T002 | T001 |
| T003, T004 | T002 |
| T005 | T002, T003 |
| T006 | T003, T004, T005 |
| T007 | T006 |
| T008 | T005, T006 |
| T009, T010 | T008 |
| T011 | T009 |
| T012 | T010 |
| T013 | T003, T004, T006 |
| T014 | T013 |
| T015 | T004, T006 |
| T016 | T003, T006 |
| **T017** | **T010, T013, T015, T016** |
| T018 | T017 |
| T019 | T016 |
| T020 | T019 |
| T021 | T018, T019 |
| T022 | T013 |
| **T023** | **T017, T022** |
| T024 | T023 |
| T025 | T015 |
| T026 | T025 |
| **T027** | **T017, T025** |
| **T028** | **T017, T023, T025** |
| T029 | T028 |
| T030 | T029 |
| T031 | T010 |
| T032 | T017, T019 |

### 关键路径（最长依赖链）

```
T001 → T002 → T003 → T006 → T016 → T017 → T023 → T028 → T029 → T030
                                                     ↑
                               T022 ────────────────┘
```

**关键路径总时长估算**: 15+10+35+10+20+90+50+35+35+15 = **315 min（约 5.3 小时）**

---

## 并行执行机会

### Phase 2 内可并行（共 85 min，并行后约 45 min）

```
T003 ──────────────────────────────────── (35 min)
T004 [P] ─────────────── (20 min)
                   T005 (15 min, 依赖 T003)
                   T006 (10 min) ── T007 [P] (30 min)
```

### Phase 3 内可并行（US1 工具层 + LLM 层 + 回调层同步推进）

```
T008 ── T009 [P] ── T011 [P]
      └ T010 [P] ── T012 [P]

T013 [P] ── T014 [P]   ← 与上方完全并行
T015 [P]               ← 与上方完全并行
T016 [P]               ← 与上方完全并行

（所有上方完成后）→ T017 → T018
```

### Phase 4–6 可并行（US2/US3/US4 互不依赖，均依赖 US1 完成）

```
T019 → T020
T021               ← 可与 T019 并行开始（T021 只依赖 T018）
T022 → T023 → T024
T025 → T026
T027
```

---

## 工时汇总

| Phase | 任务数 | 合计工时 | 并行后估算 |
|-------|--------|----------|-----------|
| Phase 1: Setup | 2 | 25 min | 25 min |
| Phase 2: Schemas | 5 | 85 min | 45 min |
| Phase 3: US1 | 11 | 390 min | 200 min |
| Phase 4: US2 | 3 | 115 min | 70 min |
| Phase 5: US3（P0） | 3 | 115 min | 85 min |
| Phase 6: US4（P0） | 3 | 75 min | 60 min |
| Phase 7: Polish | 5 | 115 min | 115 min |
| **合计** | **32** | **920 min** | **~600 min** |

*单人串行约 15 小时；关键路径约 5.3 小时（理想并行下限）；T031/T032 为补录任务，实际已完成*

---

## 实施策略

### MVP 最小路径（仅 US1）

```
Phase 1 → Phase 2 → T008~T018（US1 全部）→ T028（示例）
可验证：单次多步骤工具调用正确完成
工时估算：~430 min（约 7 小时）
```

> ⚠️ 注意：上述路径是**中间验证里程碑**，并非 Phase 1 完成标准。
> `FR-019` 要求示例演示流式输出与 ConsoleCallbackHandler，因此 **Phase 1 完成门控（T028）
> 需要 US1–US4 全部完成**（T022~T027 均为 [P0]）。
> "仅 US1"路径适合验证核心 ReAct 循环是否通畅，不能作为 Phase 1 交付物。

### 增量交付建议

1. **MVP**: Phase 1 + Phase 2 + Phase 3 → 验证算术工具示例
2. **+记忆**: Phase 4 → 验证多轮对话名字记忆
3. **+流式**: Phase 5 → 验证逐词输出
4. **+可观测**: Phase 6 → 验证 8 步事件序列
5. **收尾**: Phase 7 → 完成 `examples/01_basic_tool_use.py`
