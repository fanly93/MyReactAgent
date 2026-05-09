# Feature Specification: Phase 1 MVP — ReAct Agent 核心框架

**Feature Branch**: `001-phase1-mvp-prototype`  
**Created**: 2026-05-08  
**Status**: Draft  
**Input**: User description: "Phase 1 MVP：单 Agent + 工具调用（同步）+ 流式输出 + 多轮对话，对标 LangChain/LangGraph/OpenAI Agents SDK，纯手工实现 ReAct 循环"

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 单次多步骤任务执行 (Priority: P1)

作为 Agent 框架使用者，我希望能定义若干自定义工具，并创建一个可以自主规划、调用工具、整合结果、给出最终答案的 Agent，使我无需手动编写 Thought/Action/Observation 循环。

**Why this priority**: 这是 ReAct Agent 的核心价值主张，没有此能力框架没有存在意义。完成此故事即可交付最小可用框架。

**Independent Test**: 定义一个算术计算工具，向 Agent 提问"3 乘以 7 加上 8 等于多少"，Agent 应在最多 5 轮循环内完成工具调用并给出正确答案，无需任何人工干预。

**Acceptance Scenarios**:

1. **Given** 一个已注册算术工具的 Agent，**When** 用户提交需要多步计算的问题，**Then** Agent 依次完成思考 → 工具调用 → 观察结果 → 继续思考 → 最终答案的完整循环
2. **Given** 一个已注册多个工具的 Agent，**When** 问题需要综合多个工具的结果，**Then** Agent 能在单次会话内完成跨工具的信息整合，给出一个统一答案
3. **Given** Agent 运行中某个工具抛出异常，**When** 工具执行失败，**Then** Agent 收到结构化错误信息作为观察结果并继续循环，不崩溃、不中断
4. **Given** 单轮 LLM 响应中同时请求多个工具，**When** 工具请求到达，**Then** 框架依次执行全部工具，将所有结果一并返回模型继续推理

---

### User Story 2 - 多轮对话上下文保持 (Priority: P2)

作为框架使用者，我希望在同一个会话中连续提问，Agent 能记住之前的对话内容，无需每次重复背景信息。

**Why this priority**: 多轮对话是实际使用场景的基本要求，单轮 Agent 应用价值有限。

**Independent Test**: 第一轮告诉 Agent 一个名字，第二轮直接询问"我刚才告诉你的名字是什么"，Agent 无需重新提供名字即可正确回答。

**Acceptance Scenarios**:

1. **Given** 一个已有对话历史的 Agent 会话，**When** 用户在新一轮引用之前的信息，**Then** Agent 基于完整历史给出连贯且准确的回答
2. **Given** 会话历史达到配置的上限，**When** 新的对话轮次加入，**Then** 框架自动裁减最旧的对话，优先保留系统提示和最近对话，Agent 继续正常运行
3. **Given** 两个并发运行的 Agent 会话，**When** 两个会话同时进行工具调用和对话，**Then** 各自的对话历史完全独立，一个会话的内容不会出现在另一个会话中

---

### User Story 3 - 实时流式输出 (Priority: P3)

作为框架使用者，我希望在 Agent 生成回答时能实时看到文字流式输出，而不是等待全部生成完成后一次性显示，改善长推理过程的等待体验。

**Why this priority**: 流式输出显著改善用户体验，对耗时较长的推理任务尤为重要。

**Independent Test**: 向 Agent 提交一个需要多步推理的问题，终端应逐词实时打印输出；若截断输出流，已输出的内容应是完整的句子片段，而非等待结束后一次性出现。

**Acceptance Scenarios**:

1. **Given** Agent 正在生成较长的思考过程，**When** 流式输出开启，**Then** 用户能看到文字逐步出现，整体感知延迟明显低于非流式模式
2. **Given** Agent 在流式输出中触发工具调用，**When** 工具调用完成后继续生成，**Then** 整个流式过程保持连续，工具调用前后的内容均正常流式呈现

---

### User Story 4 - 执行过程可观测 (Priority: P3)

作为框架使用者，我希望通过注册回调函数来监听 Agent 的完整执行过程（每次 LLM 调用、每次工具调用、错误事件、会话结束），方便日志记录、调试和后续监控接入。

**Why this priority**: 生产级 Agent 必须具备可观测性，也是后续接入 OpenTelemetry 等监控系统的基础接口。Phase 1 预留接口，即使暂时只有控制台输出，也能避免后续大规模重构。

**Independent Test**: 注册内置的控制台回调，运行一次含工具调用的 Agent，终端应依次打印"`on_agent_start` → `on_llm_start` → `on_llm_end` → `on_tool_start` → `on_tool_end` → `on_llm_start` → `on_llm_end` → `on_agent_end`"的事件序列。

**Acceptance Scenarios**:

1. **Given** 注册了回调处理器的 Agent，**When** Agent 完成一次含工具调用的完整循环，**Then** 所有 7 类生命周期事件（`on_agent_start`、`on_llm_start`、`on_llm_end`、`on_tool_start`、`on_tool_end`、`on_agent_end`、`on_error`）均触发对应回调，且事件顺序符合 ReAct 循环语义
2. **Given** 工具执行抛出异常，**When** 错误发生，**Then** 框架捕获异常并转化为 `ToolResult(success=False)`，`on_tool_end` 回调被触发（携带 `success=False` 和错误信息），ReAct 循环继续执行；`on_error` 回调不触发（`on_error` 仅用于 LLM 返回格式错误等框架内部错误路径）
3. **Given** 未注册任何回调，**When** Agent 正常运行，**Then** Agent 行为与注册回调时完全一致，无性能损耗

---

### Edge Cases

- 工具调用参数不符合声明的参数格式时，应验证失败并返回结构化错误作为观察，模型可据此修正参数重试
- `max_iterations` 达到上限时，若 LLM 在"请总结"提示后仍无法给出答案，返回当前已有的最佳内容
- 同一轮 LLM 响应中多个工具调用，其中一个执行失败时，其余工具的成功结果仍应正常返回给模型
- 工具列表为空时（`tools=[]`），Agent 作为纯文本对话助手运行，LLM 不接收任何工具 schema，ReAct 循环在 `finish_reason="stop"` 时直接返回，不进入工具调用分支；框架不发出警告，此为合法使用模式
- 系统提示极长导致单条消息已接近上下文限制时，框架通过 `on_error` 事件发出一次 warning（`data.warning=true`），系统提示仍优先保留，不抛出异常
- LLM API 调用失败（超时、HTTP 5xx、rate limit 429 等）时，Phase 1 在 LLMClient 初始化时配置 OpenAI SDK 的 `max_retries=3` 参数，委托 SDK 对 `RateLimitError`、`APIConnectionError`、`APITimeoutError` 执行指数退避重试；错误分类策略、fallback 模型链和熔断器在 Phase 4 引入

---

## Requirements *(mandatory)*

### Functional Requirements

**核心 ReAct 循环**

- **FR-001**: 框架 MUST 支持完整的多轮 ReAct 循环，每轮包含模型思考、工具调用请求、工具执行、结果观察四个阶段，循环直至模型给出最终答案
- **FR-002**: 框架 MUST 在模型自然完成推理（无更多工具调用需求）时自动终止循环并输出最终答案
- **FR-003**: 框架 MUST 支持可配置的最大迭代次数，默认值为 **10 轮**，开发者可在创建 Agent 时通过参数自定义；达到上限时，框架向模型发送"请根据已有信息给出最终答案"的指令，正常输出结果，不抛出异常
- **FR-004**: 框架 MUST 支持同步流式输出，LLM 生成内容实时传递给调用方，无需等待完整响应

**多轮对话与上下文管理**

- **FR-005**: 框架 MUST 支持同一会话内的多轮对话，完整保留并利用历史对话上下文
- **FR-006**: 框架 MUST 内置上下文滑动窗口截断策略，消息数上限默认值为 **20 条**，开发者可通过配置自定义；当对话历史超出上限时自动裁减，保留优先级为：系统提示（永远保留）> 工具调用配对消息 > 最近 N 轮对话。"工具调用配对消息"精确定义为：`assistant 消息（含 tool_calls 字段）` + **该轮所有 `tool` 结果消息**，共 **1+N 条**（N = 该轮工具调用数量），作为原子单元不得拆开；触发该次工具调用的 `user` 消息不纳入配对保护范围；在 20 条总上限内，最近 `keep_last_n=6` **轮**完整对话（每轮含用户消息和模型回复，约 12 条消息）同样受保护不得截断；`keep_last_n` 为独立配置参数，与消息总上限（默认 20 条）互不影响，均可在创建 Agent 时通过参数自定义
- **FR-006b**: 框架 MUST 对工具返回的文本内容做长度保护，默认上限为 **8000 字符**（Phase 1 字符级近似，Phase 3 升级为 token-aware，见 `specs/deferred-items.md` DI-001）；超出时截断并在末尾附加提示通知模型内容已被截断及原始长度；上限通过常量 `MAX_TOOL_OUTPUT_CHARS` 定义，Phase 1 不支持运行时自定义（Phase 3 引入可配置参数及工具级覆盖）
- **FR-007**: 框架 MUST 在任何截断操作下保证会话系统提示不被裁减
- **FR-007b**: 上下文截断的保护优先级从高到低为：系统提示（永远保留）> tool_call 原子对（assistant + 关联 tool 消息，不可拆分）> 最近 `keep_last_n` 轮对话 > 其余中间消息（可截断）。当单个 tool_call 原子对的消息数（1+N 条）本身超过 `max_messages` 上限时，框架 MUST 保留该原子对完整内容，实际消息数可短暂超出上限；此时框架通过 `on_error` 事件发出一次 warning（`data.warning=true`），不抛出异常，循环继续正常运行

**工具系统**

- **FR-008**: 框架 MUST 允许开发者使用装饰器方式定义工具，自动从函数签名和文档字符串生成工具名称、描述和参数规范
- **FR-009**: 框架 MUST 允许开发者使用类继承方式定义工具，完全手动控制名称、描述和参数规范（作为装饰器方式的逃生口）
- **FR-010**: 框架 MUST 支持模型在单轮响应中请求多个工具，框架按顺序执行全部工具，将所有结果统一返回
- **FR-011**: 框架 MUST 捕获工具执行中的所有异常，将其转化为结构化错误信息返回给模型，ReAct 循环不得因工具异常崩溃
- **FR-012**: 框架 MUST 在执行前验证工具调用参数与工具声明的参数规范是否匹配，不匹配时返回结构化验证错误

**可观测性**

- **FR-013**: 框架 MUST 提供生命周期回调接口，涵盖 7 类事件：`on_agent_start`（Agent 会话开始）、`on_llm_start`（LLM 请求发送前）、`on_llm_end`（LLM 响应接收完毕后）、`on_tool_start`（工具执行前）、`on_tool_end`（工具执行后，无论成功或失败均触发，失败时 `data` 携带 `success=False` 和错误信息）、`on_agent_end`（Agent 会话完成）、`on_error`（框架内部错误，如 LLM 返回格式错误、工具参数验证失败等）。触发路径区分：工具执行异常由框架捕获并转化为 `ToolResult(success=False)`，通过 `on_tool_end` 上报，不触发 `on_error`；`on_error` 仅在 LLM 返回无效 JSON tool_call 等框架内部解析错误时触发。流式与非流式模式下回调行为对称：`on_llm_start` 在 LLM 请求发送前触发一次；`on_llm_end` 在完整响应接收完毕后触发一次（流式场景下为流结束、内容拼接完成后），携带完整内容；调用方无需区分两种模式。**回调异常隔离**：回调方法抛出的任何异常 MUST 被框架捕获并静默忽略，不得影响 Agent 主流程；多个 `BaseCallbackHandler` 同时注册时，单个处理器的异常不影响后续处理器的执行，所有处理器按 `callbacks` 列表注册顺序串行调用
- **FR-014**: 所有回调事件 MUST 携带统一结构的事件载荷，包含以下 6 个字段：事件类型（`event`）、数据（`data`）、时间戳（`timestamp`，ISO-8601 格式）、会话标识符（`session_id`）、本次运行标识符（`run_id`，每次 `agent.run()` 调用唯一生成）、追踪跨度标识符（`span_id`，Phase 1 可为空字符串，Phase 4 接入 OpenTelemetry 时填充）；`session_id` 与 Agent 实例绑定，在整个会话生命周期内保持不变；事件载荷字段结构 MUST 不随阶段变更（允许新增字段，禁止删除或重命名现有字段）
- **FR-015**: 框架 MUST 内置控制台回调实现，供开发者开箱即用地观察 Agent 执行过程

**会话隔离**

- **FR-016**: 框架 MUST 保证不同会话之间零状态共享，禁止存在任何全局可变状态
- **FR-017**: 工具集合和对话历史 MUST 以会话为单位独立创建，支持通过工厂函数模式按需生成

**质量与可验证性**

- **FR-018**: 框架核心模块（工具系统、对话记忆、LLM 交互、Agent 循环）MUST 各有对应单元测试；LLM 交互通过模拟对象测试，集成测试通过环境变量门控
- **FR-019**: 框架 MUST 提供端到端示例（`examples/01_basic_tool_use.py`），演示工具定义、Agent 创建、多轮对话和流式输出的完整使用流程
- **FR-020**: 框架消息数据模型的 `content` 字段 MUST 在 Phase 1 定义为 `Union[str, list[ContentPart]]` 类型；`ContentPart` 为多模态内容块联合类型（含 `TextContentPart`、`ImageContentPart`、`AudioContentPart`），Phase 1 仅处理 `str` 分支，遇到 `list[ContentPart]` 时抛出明确的 `NotImplementedError`；工具调用结果的返回值类型同步预留此扩展点

**循环控制**

- **FR-021**: 框架 MUST 在 Phase 1 定义 `NextStep` 枚举类型，将 ReAct 循环的四种走向显式建模为独立状态：`STOP`（终止并输出结果）、`CONTINUE`（执行工具后继续循环）、`HANDOFF`（移交控制权至其他 Agent，Phase 2 实现）、`INTERRUPT`（等待人工确认，Phase 4 实现）；`STOP` 和 `CONTINUE` 在 Phase 1 完整实现，`HANDOFF` 和 `INTERRUPT` 为占位实现：Agent 循环内触发这两种状态时，框架抛出 `NotImplementedError`，错误消息明确说明所属阶段（如 `"NextStep.HANDOFF is not implemented until Phase 2"`）；调用方在 Phase 1 无需处理此异常，可视为不会触发的保留路径；枚举定义不得缺失

**工具属性声明**

- **FR-022**: 所有工具基类 MUST 在 Phase 1 声明以下属性：`is_destructive: bool`（是否为不可逆操作，默认 `False`）和 `permission: Literal["read", "write", "destructive"]`（权限级别，默认 `"read"`）；Phase 1 不实现基于这些属性的权限门控或人工确认逻辑，但属性 schema 必须在基类层面完整声明，确保 Phase 4 在不修改调用方代码的前提下激活对应能力。**两者的语义关系**：`is_destructive` 是布尔快捷标记，专门描述操作是否不可逆（删除、覆盖等）；`permission` 是更细粒度的分级标签，描述所需的访问权限范围（`"read"` = 只读、`"write"` = 有副作用但可恢复、`"destructive"` = 不可逆高风险）。两者互补而非冗余：`is_destructive=True` 通常伴随 `permission="destructive"`，但也允许 `is_destructive=True, permission="write"`（如覆盖写）；Phase 4 激活门控时，`is_destructive` 决定是否触发 HITL 确认，`permission` 决定门控策略类型；两者均可独立设置，框架不强制一致性约束

### Key Entities

- **Agent 会话（Session）**：一次 Agent 运行的完整上下文，包含系统提示、对话历史、工具集合和运行配置；会话间完全隔离，无共享状态。`session_id` 在会话创建时由框架自动生成（UUID），开发者可在创建 Agent 时传入自定义值（可选参数）；未传入时使用自动生成值
- **工具（Tool）**：可被 Agent 调用的函数单元，包含名称、描述、参数规范和执行逻辑；必须声明 `is_destructive: bool`（是否不可逆，默认 `False`）和 `permission: Literal["read", "write", "destructive"]`（权限级别，默认 `"read"`）两个属性；支持装饰器和类继承两种定义形式
- **工具调用结果（Tool Result）**：工具执行的标准化输出，包含成功标志、返回值（成功时）或结构化错误信息（失败时）；返回值的类型为 `MessageContent`（即 `Union[str, list[ContentPart]]`），Phase 1 只使用 `str` 分支，Phase 4 起工具可返回图像等多模态内容
- **回调事件（Callback Event）**：框架生命周期节点触发的标准化消息，包含 6 个字段：事件类型（`event`）、数据载荷（`data`）、时间戳（`timestamp`）、会话标识符（`session_id`）、运行标识符（`run_id`）、追踪跨度标识符（`span_id`，Phase 1 可为空字符串）
- **对话历史（Conversation History）**：会话内的消息序列，包含系统提示、用户消息、模型回复和工具调用记录，受滑动窗口策略管理。每条消息的 `content` 字段类型为 `Union[str, list[ContentPart]]`——Phase 1 只使用 `str` 分支，`list[ContentPart]` 作为多模态扩展点在数据模型层预留，Phase 4 启用时无需修改调用方代码

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 开发者能在 15 行以内的代码创建一个带有自定义工具的可运行 Agent，并执行一次完整的 ReAct 循环
- **SC-002**: 端到端示例 `examples/01_basic_tool_use.py` 在具备有效 API Key 的环境中直接运行成功，演示至少 3 种工具的完整多轮 ReAct 循环
- **SC-003**: 工具执行异常不导致 Agent 循环崩溃，100% 的工具异常场景转化为结构化观察并继续循环
- **SC-004**: 并发创建 10 个独立 Agent 会话并各自执行工具调用，验证各会话历史无交叉污染；此标准可在无真实 API 密钥的环境中通过 mock LLMClient 验证，属单元测试范畴，不依赖集成测试
- **SC-005**: 单次含工具调用的 Agent 运行，触发的生命周期事件序列与声明的 7 类事件（`on_agent_start`、`on_llm_start`、`on_llm_end`、`on_tool_start`、`on_tool_end`、`on_agent_end`、`on_error`）完全吻合，无遗漏
- **SC-006**: 核心模块单元测试可在无真实 API 密钥的环境中全部通过，测试通过率 100%

---

## Clarifications

### Session 2026-05-08

- Q: 流式输出时 on_llm_start / on_llm_end 的触发时机？ → A: on_llm_start 请求发送前触发一次，on_llm_end 流结束内容拼接完成后触发一次，携带完整内容；流式与非流式对称
- Q: max_iterations 和滑动窗口 N 的默认值？ → A: max_iterations 默认 10 轮，滑动窗口默认 20 条消息，均支持开发者创建 Agent 时自定义
- Q: LLM API 调用失败（超时 / 5xx / 429）时框架的处理策略？ → A: Phase 1 配置 SDK `max_retries=3` 委托实现基础指数退避重试（覆盖 RateLimitError / APIConnectionError / APITimeoutError）；错误分类、fallback 链、熔断器在 Phase 4 引入
- Q: session_id 的生成和提供方式？ → A: 框架自动生成 UUID 作为默认，开发者可在创建 Agent 时传入自定义 session_id（可选参数）
- Q: 滑动窗口截断时"工具调用配对"的精确边界？ → A: assistant（含 tool_calls）+ 该轮所有 tool 结果消息，共 1+N 条（N = 工具调用数量），作为原子单元不得拆开；触发该次工具调用的 user 消息不纳入配对保护

---

## Assumptions

- 目标使用者为 Python 开发者，熟悉函数、类和装饰器的基本用法
- 框架在 Phase 1 仅支持同步执行模式，含**同步流式**输出（`stream=True` 返回同步迭代器，无 `async/await`）；Phase 2 将流式升级为**异步流式**（新增 `async def run_stream()`，基于 `async/await`），二者在接口签名和使用方式上有本质区别；CLAUDE.md 中 Phase 2"实时流式输出"目标指此异步升级，而非 Phase 1 已有的同步流式
- LLM 服务提供商兼容 OpenAI 聊天补全接口（Chat Completions API），并支持工具调用（Tool Use）能力
- API Key 和模型配置由使用者通过环境变量提供，框架不负责凭证存储或管理
- Phase 1 不包含跨会话的持久化记忆，会话结束后对话历史不保留（持久化记忆在 Phase 3 引入）
- Phase 1 不包含多 Agent 编排，仅支持单 Agent 运行（多 Agent 协作在 Phase 2 引入）
- 上下文截断基于消息条数而非精确 token 计数，精确 token 管理在后续阶段优化
- Human-in-the-Loop（人工确认高风险操作）在 Phase 4 引入，Phase 1 所有工具均自动执行
- Phase 1 通过在 LLMClient 初始化时配置 OpenAI SDK 的 `max_retries=3` 参数实现基础指数退避重试，等同于框架层重试能力；Phase 4 在此基础上增加错误分类重试、fallback 模型链和熔断器

---

## Out of Scope

本节明确列出 Phase 1 **不实现**的能力，避免需求蔓延，同时为后续阶段预留清晰边界。

### 延至 Phase 2（流式响应 + 多 Agent）

- **异步执行**：不引入 `async/await`，所有操作均为同步调用（同步流式输出通过同步迭代器实现，属 Phase 1 范围，不在此限）
- **多 Agent 编排**：不支持 Orchestrator-Worker 模式、Agent 嵌套或 Agent 间通信
- **Agent-as-Tool**：不支持将子 Agent 封装为工具供上层 Agent 调用
- **并发工具执行**：多工具调用仅顺序执行，不并发执行

### 延至 Phase 3（长短期记忆）

- **跨会话持久化记忆**：会话结束后对话历史不保留，无法在下次对话中恢复
- **向量数据库集成**：不集成 ChromaDB、FAISS 等向量存储，不支持语义检索
- **长期记忆召回**：不支持基于语义相似度检索历史会话信息
- **LLM 摘要压缩**：上下文截断仅用滑动窗口，不使用 LLM 对历史进行摘要压缩

### 延至 Phase 4（生产级）

- **可观测性平台接入**：不集成 OpenTelemetry、LangSmith 等外部监控平台（仅提供接口预留）
- **Human-in-the-Loop**：不支持对高风险工具操作暂停等待人工确认
- **高级重试策略**：不实现错误分类重试、fallback 模型链或熔断器（基础指数退避已在 Phase 1 通过 SDK `max_retries=3` 配置实现）
- **MCP 协议支持**：不接入 Model Context Protocol，不支持 MCP Server 工具加载
- **Skill 打包**：不支持标准化 Skill 格式，不具备 Skill 分发或复用能力
- **Web 服务层**：不提供 FastAPI 接口、SSE 流式端点或 REST API
- **工具权限分级**：不实现 read / write / destructive 权限标记和执行确认机制
- **Prompt Injection 防护**：不内置恶意输入检测或工具输出净化机制
- **多模态输入**：Phase 1-3 仅支持文本输入；图像、音频、视频等非文本输入在 Phase 4 或后续版本引入

### 永久 Out of Scope（设计约束，所有阶段均不实现）

- **Agent 框架依赖**：禁止引入 LangChain、LangGraph、AutoGen、CrewAI 等 Agent 框架库
- **代码执行沙盒**：不内置代码隔离执行环境（如需可作为自定义工具实现）
- **凭证管理**：不负责 API Key 的存储、轮换或加密，由使用者自行管理
