# 竞品调研汇总报告

> **来源报告**
> - Teammate 1：`teammate1_agent_design_philosophy.md`（设计理念与哲学，7 个维度）
> - Teammate 2：`teammate2_reference_projects_analysis.md`（5 个开源项目源码分析，8 个维度）
>
> **汇总日期**：2026-05-08  
> **汇总目的**：为 MyReactAgent 各阶段实现提供决策依据

---

## 一、跨报告共识：两位 Teammate 的一致结论

两份报告从「理念」和「实现」两个视角独立调研，以下结论高度吻合，置信度最高。

### 1. 零全局可变状态是架构红线

- **设计哲学**（Teammate 1）：全局可变状态是生产事故的根源，LangChain 早期因全局 Memory 单例导致用户对话混入；LangGraph 通过 `thread_id` 隔离、AutoGen 0.4 完全重写才解决此问题。
- **源码印证**（Teammate 2）：5 个项目中表现最好的是 openai-agents，每次 `Runner.run()` 创建独立执行上下文；hermes-agent 的 `ToolRegistry` 虽是单例但用 `threading.RLock` 保证线程安全；LangChain 旧版 Memory 是反面教材。
- **对 MyReactAgent 的结论**：`ConversationMemory`、`ToolRegistry` 必须通过工厂函数创建，通过构造函数注入，**Phase 1 第一行代码就要坚守，后期修复代价等同于大规模重构**。

### 2. AgentTool 模式是多 Agent 的最优抽象

- **设计哲学**（Teammate 1）：子 Agent 包装为 Tool 使 Orchestrator 完全复用 ReAct 循环，架构统一，代码量最小。OpenAI Agents SDK 提供了 `as_tool()` 和 `handoff` 两种模式，区别在于控制权归属。
- **源码印证**（Teammate 2）：ADK 的 `AgentTool`（`agent_tool.py` 第 94–286 行）是最完整的参考实现，约 50 行核心代码，展示了子 Agent 独立 Session + 状态双向同步的完整方式；openai-agents 的 `Agent.as_tool()` 极简，5 行即可完成子 Agent 包装。
- **对 MyReactAgent 的结论**：Phase 2 的 `agent/orchestrator.py` 直接参考 ADK 的 `AgentTool` 实现，Orchestrator 继承 ReactAgent 复用循环逻辑，无需另立架构。

### 3. 工具错误必须 Observation 化，不能崩溃

- **设计哲学**（Teammate 1）：工具失败是 ReAct 的信息来源，三层处理：重试 → 降级 → 错误作为 Observation 反馈 LLM。
- **源码印证**（Teammate 2）：openai-agents 的 `_failure_error_function` 将工具异常转为字符串返回给模型（`tool.py` 第 1475 行）；hermes-agent 有 `classify_api_error()` 区分 7 种错误类型并触发不同处理路径；ADK 的 `FunctionResponse.response` 返回错误信息。
- **对 MyReactAgent 的结论**：`tools/registry.py` 的 `execute()` 方法必须全量捕获异常，封装为 `ToolResult(success=False, error="...")` 返回，保证 ReAct 循环永远不因工具失败而崩溃。

### 4. Callback Hook 必须从 Phase 1 预留，不能事后插入

- **设计哲学**（Teammate 1）：LangChain 的 `BaseCallbackHandler` 是最成熟的非侵入式实现，核心代码零 trace 逻辑，事后扩展无需修改核心代码。Google ADK 有 4 类 Callback（`before/after_model/tool_callback`）。
- **源码印证**（Teammate 2）：openai-agents 的 `RunHooks`（`lifecycle.py`）提供 `on_agent_start`/`on_tool_start`/`on_tool_end` 等钩子；deepagents 的 `AgentMiddleware` 中间件栈是另一种等价设计。
- **对 MyReactAgent 的结论**：Phase 1 在 `on_llm_start`、`on_tool_call`、`on_tool_result`、`on_final_answer` 四个关键点插入空 Callback 调用，Handler 列表默认空列表。**宪法第 6 条不是 Phase 4 的事，是 Phase 1 的设计约束。**

---

## 二、关键分歧点：两份报告的侧重差异

### 分歧 1：Schema 自动生成的深度

- **Teammate 1** 给出了抽象原则：自动生成为主，手动声明为逃生口，处理好 `Optional`/`Union`/`Literal` 边缘情况。
- **Teammate 2** 给出了具体实现路径：直接参考 openai-agents 的 `function_schema.py`，用 `griffe`（解析 docstring）+ `pydantic.create_model()`（动态生成参数模型）+ `model_json_schema()`（导出 JSON Schema）的三步链路。
- **综合结论**：MyReactAgent 的 `utils/schema.py` 可以直接以 openai-agents 的 `function_schema.py` 为参考实现，无需从零设计。

### 分歧 2：ToolRegistry 的形态

- **Teammate 1** 倾向依赖注入（工具作为构造参数传入），理由是更显式、更易测试、天然隔离。
- **Teammate 2** 发现实践中 5 个项目全部是**列表传入 + 运行时构建 lookup map**，没有一个使用全局注册中心单例（hermes-agent 虽有单例但这是反面案例）。
- **综合结论**：采用「工具列表传入构造函数 + 运行时 `ToolRegistry` 实例」的混合方案——`ToolRegistry` 是实例级对象（不是全局单例），`Agent(tools=[...])` 构造时从列表初始化，同时支持 `registry.register()` 动态添加。这满足显式注入、会话隔离、动态扩展三个要求。

### 分歧 3：流式处理的实现时机

- **Teammate 1** 强调流式和非流式接口需统一，`async def run_stream()` 与 `run()` 并存，Phase 2 引入。
- **Teammate 2** 发现两种主流模式：openai-agents 用 `asyncio.Queue[StreamEvent]` 统一；langchain 用 `AIMessageChunk.__add__()` 合并 delta 后再统一为 `AIMessage`。
- **综合结论**：Phase 2 的 `llm/streaming.py` 优先参考 LangChain 的 `AIMessageChunk` 模式实现 tool_call 碎片组装（简洁明了），再用 `asyncio.Queue` 统一流式/非流式对外接口，与宪法第 8 条一致。

---

## 三、各阶段设计决策优先级矩阵

### Phase 1（当前阶段）— 必须锁定

| 决策项 | 来源 | 参考实现 | 补救难度 |
|--------|------|---------|---------|
| 零全局可变状态（工厂函数创建 Memory/Registry） | 双方共识 | openai-agents `Runner.run()` | **极高** |
| 工具错误全量捕获，返回 `ToolResult(success=False)` | 双方共识 | openai-agents `tool.py:1475` | 中 |
| Callback Hook 四个预留点（空实现可以） | 双方共识 | LangChain `BaseCallbackHandler` | **高** |
| ReAct 终止：`stop_reason` 为主，`max_iterations` 为兜底（发送总结提示） | Teammate 1 | openai-agents `run_steps.py` NextStep 枚举 | 低 |
| Schema 自动生成：griffe + pydantic 三步链路 | Teammate 2 | openai-agents `function_schema.py` | 低 |
| 统一事件格式 Schema 在 Phase 1 确定 | Teammate 1 | 自定义（符合 CLAUDE.md 规划） | 低 |

### Phase 2 — 流式 + 多 Agent

| 决策项 | 来源 | 参考实现 | 优先级 |
|--------|------|---------|--------|
| AgentTool：子 Agent 独立 Session + 状态同步 | 双方共识 | adk-python `agent_tool.py:94-286` | 高 |
| 流式 tool_call 碎片组装（按 index 合并） | Teammate 2 | langchain `AIMessageChunk.__add__()` | 高 |
| 同步/异步透明化（`asyncio.to_thread()` 包装同步工具） | Teammate 2 | openai-agents `tool.py:1865` | 中 |
| NextStep 枚举模式取代 if/else 字符串判断 | Teammate 2 | openai-agents `run_steps.py` | 中 |

### Phase 3 — 记忆系统

| 决策项 | 来源 | 参考实现 | 优先级 |
|--------|------|---------|--------|
| `BaseMemoryService` ABC（可插拔向量后端） | Teammate 2 | adk-python `base_memory_service.py:44` | 高 |
| Pre-loop 注入 Top-3 记忆 + `recall_memory` 工具动态召回双轨制 | Teammate 1 | hermes-agent `memory_manager.py:prefetch_all()` | 高 |
| 短期记忆截断：保护 System Prompt + 首尾 N 条 + 所有 tool_calls | Teammate 1 | hermes-agent `context_compressor.py` | 高 |
| 记忆元数据必须含 `user_id`/`session_id`/`timestamp` | Teammate 1 | ADK `BaseMemoryService` 设计 | 中 |

### Phase 4 — 生产级

| 决策项 | 来源 | 参考实现 | 优先级 |
|--------|------|---------|--------|
| RetryPolicy 策略组合器（`any()`/`all()` 组合） | Teammate 2 | openai-agents `retry.py:231` | 高 |
| 错误分类器（区分 rate_limit/context_overflow/auth/network） | Teammate 2 | hermes-agent `error_classifier.py` | 高 |
| HITL：`is_destructive` 标记 + 状态持久化 + 异步恢复 | Teammate 1 | LangGraph `Interrupt + Checkpointer` 设计 | 中 |
| `before/after_model/tool` 四类 Callback 完整实现 | Teammate 2 | adk-python `llm_agent.py:72-130` | 中 |
| Prompt Injection：Guardrail 只接受原始用户输入验证 | Teammate 1 | OpenAI Agents SDK Guardrails | 中 |

---

## 四、LangGraph 源码补充共识（2026-05-08 新增）

LangGraph 源码分析完成后，新增以下共识条目：

### 5. interrupt() 节点重执行：HITL 必须保证幂等性

- **源码实证**：LangGraph `interrupt()` 在 resume 时**从节点起点重新执行**，interrupt 前的副作用会被重复触发（`types.py` L801-867 文档明确说明）。
- **对 MyReactAgent 的结论**：Phase 4 实现 HITL 时，含 `interrupt` 的节点内所有副作用（数据库写入、API 调用等）必须满足幂等性约束。实现时应将副作用后置于 interrupt 之后，或在 interrupt 前记录已执行状态。

### 6. 工具错误模板化是最成熟的业界方案

- **源码实证**：LangGraph `ToolNode` 预定义了 4 套错误模板（`tool_node.py` L108-121）：`INVALID_TOOL_NAME_ERROR_TEMPLATE`、`TOOL_CALL_ERROR_TEMPLATE`、`TOOL_EXECUTION_ERROR_TEMPLATE`、`TOOL_INVOCATION_ERROR_TEMPLATE`，覆盖了工具调用的所有失败场景，均返回字符串 ToolMessage 而非抛出异常。
- **对 MyReactAgent 的结论**：Phase 1 的 `tools/registry.py` 应预定义错误模板常量，与 LangGraph 保持同等健壮性。

### 7. RetryPolicy 的 retry_on 可调用设计优于类型列表

- **源码实证**：LangGraph `RetryPolicy.retry_on` 支持 `Callable[[Exception], bool]`（`types.py` L422-424），可在运行时动态判断（解析 HTTP status code、错误码分类）。
- **对 MyReactAgent 的结论**：`llm/retry.py` 的 `RetryPolicy` 应从一开始就设计为支持可调用 `retry_on`，而非仅限于异常类型列表。

---

## 五、可直接复用的源码路径索引

以下文件可在实现 MyReactAgent 时直接参考（Teammate 2 已验证内容）：

| MyReactAgent 模块 | 参考文件 | 关键内容 |
|------------------|---------|---------|
| `utils/schema.py` | `reference_projects/openai-agents-python/src/agents/function_schema.py` | griffe + pydantic create_model 三步链路 |
| `tools/base.py` | `reference_projects/openai-agents-python/src/agents/tool.py`（第 282–406 行） | FunctionTool dataclass，failure_error_function，asyncio.to_thread |
| `tools/base.py`（错误模板） | `reference_projects/langgraph/libs/prebuilt/langgraph/prebuilt/tool_node.py`（L108-121） | 4 套工具错误字符串模板，覆盖所有失败场景 |
| `tools/registry.py` | `reference_projects/hermes-agent/tools/registry.py`（第 143–260 行） | threading.RLock + generation 计数器 |
| `agent/react_agent.py` | `reference_projects/openai-agents-python/src/agents/run_internal/run_steps.py` | NextStep 枚举控制流 |
| `llm/streaming.py` | `reference_projects/langchain/libs/core/langchain_core/messages/`（AIMessageChunk） | tool_call delta 合并逻辑 |
| `agent/orchestrator.py` | `reference_projects/adk-python/src/google/adk/tools/agent_tool.py`（第 94–286 行） | AgentTool 独立 Session + 状态同步 |
| `memory/short_term.py` | `reference_projects/langgraph/libs/langgraph/langgraph/graph/message.py`（add_messages） | 消息追加 Reducer 设计，显式声明合并语义 |
| `memory/checkpoint.py` | `reference_projects/langgraph/libs/checkpoint/langgraph/checkpoint/base/__init__.py`（L167-363） | BaseCheckpointSaver 4 核心方法 + put_writes 增量容错 |
| `memory/long_term.py` | `reference_projects/adk-python/src/google/adk/memory/base_memory_service.py` | BaseMemoryService ABC 接口设计 |
| `llm/retry.py` | `reference_projects/openai-agents-python/src/agents/retry.py` | RetryPolicy 策略组合器 |
| `llm/retry.py`（retry_on） | `reference_projects/langgraph/libs/langgraph/langgraph/types.py`（L406-426） | Callable retry_on 设计，支持运行时动态判断 |
| `agent/hitl.py` | `reference_projects/langgraph/libs/langgraph/langgraph/types.py`（L748-870） | Command + interrupt() + 节点重执行幂等性约束 |

---

## 五、值得关注的反面教材

以下是调研中发现的设计陷阱，应在 MyReactAgent 中主动规避：

1. **LangChain 早期 Memory 单例**：模块级全局 `ConversationMemory` 导致多用户会话混入，是全局可变状态危害的经典案例。
2. **hermes-agent 的 Schema 手动声明**：所有工具 schema 以 `dict` 手动编写，Schema 与实现分离导致漂移风险，开发效率低。
3. **openai-agents 无内置 token 计数**：将上下文管理完全交给服务端（`conversation_id`），导致框架无法感知和控制上下文窗口，与宪法第 13 条冲突。
4. **deepagents 过度依赖上层框架**：核心循环、工具系统、消息格式全部委托给 LangGraph/LangChain，自身无实质实现，可读性差，学习价值低。

---

*本报告由 Lead 综合 Teammate 1（设计哲学）和 Teammate 2（源码分析）两份报告生成，不包含独立原创调研内容。*  
*详细内容请参阅各 Teammate 报告。*
