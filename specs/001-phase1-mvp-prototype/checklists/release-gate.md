# Phase 1 发布门控清单: MyReactAgent MVP — ReAct Agent 核心框架

**Purpose**: Phase 1 正式发布前的需求质量门控——验证 spec、plan、contracts 三份文档的需求表述是否完整、清晰、一致、可测量，作为 Phase 1 → Phase 2 交接的可追溯证据  
**Created**: 2026-05-09  
**Feature**: [spec.md](../spec.md) | [plan.md](../plan.md) | [contracts/public-api.md](../contracts/public-api.md)  
**Depth**: 正式发布门控（Formal Release Gate）  
**Focus**: 公共 API 契约质量 · 错误处理需求清晰度 · 测试规范可验证性  

---

## 一、公共 API 契约完整性与清晰度

- [x] CHK001 - `ReactAgent` 构造函数的所有参数（`tools`、`system_prompt`、`session_id`、`max_iterations`、`max_messages`、`keep_last_n`、`callbacks`、`model`、`base_url`、`api_key`）是否均已在 contracts/public-api.md §2.1 中文档化，并标注默认值？ [Completeness, Spec §FR-001]

- [x] CHK002 - 显式传参与环境变量之间的优先级规则（`api_key` > `OPENAI_API_KEY` 等）是否在 contracts/public-api.md 中有明确表述，而非仅在宪法原则 III 中隐含？ [Clarity, Spec §5]

- [x] CHK003 - `run_stream()` 返回类型为同步迭代器 `Iterator[str]`（Phase 1）这一关键约束是否在 contracts/public-api.md §2.3 中以"STABLE"标注并与 Phase 2 异步升级的区别加以说明？避免调用方混淆。 [Clarity, Spec §FR-004 / Assumption]

- [x] CHK004 - `@tool` 装饰器在以下边界条件下的行为是否均已在 contracts/public-api.md §1.1 中文档化：① 函数无类型注解、② 缺少文档字符串、③ 以 `@tool(is_destructive=True, permission="destructive")` 带参调用？ [Completeness, Spec §FR-008]

- [x] CHK005 - 工具列表为空时（`tools=[]`）的 Agent 行为是否在 contracts/public-api.md 或 spec 中有明确描述（纯对话模式，不触发工具循环）？ [Coverage, Edge Case, Gap]

- [x] CHK006 - `BaseTool.execute()` 的 `args` 参数中框架自动注入的 `_tool_call_id` 字段是否在 contracts/public-api.md §1.2 中明确说明，而非仅作为示例出现？ [Clarity, Spec §FR-009]

- [x] CHK007 - `run_stream()` 多轮对话时历史是否自动累积（与 `run()` 对称）这一行为是否在 contracts/public-api.md §2.3 中明确记载，而非仅在 §2.4 多轮对话节中隐含？ [Completeness, Spec §FR-005]

- [x] CHK008 - `STABLE` 与 `RESERVED` 标注是否在 contracts/public-api.md 中使用一致，所有 Phase 1 承诺稳定的接口是否均带 `STABLE`，占位实现是否均带 `RESERVED`？ [Consistency, Spec §contracts/public-api.md]

---

## 二、错误处理需求清晰度

- [x] CHK009 - `on_tool_end(success=False)`（工具执行异常路径）与 `on_error`（LLM 返回格式错误路径）的触发条件是否在 spec FR-013 中已明确区分，且与 contracts/public-api.md 错误处理契约表（§6）中的描述一致？ [Consistency, Spec §FR-013 / §6]

- [x] CHK010 - `on_tool_end` 在 `success=False` 时的 `data` 载荷结构是否已在 spec FR-013 或 contracts/public-api.md §4 中明确定义（至少包含哪些字段）？ [Completeness, Spec §FR-013]

- [x] CHK011 - `max_iterations` 安全兜底时发送给 LLM 的追加消息文本是否在 spec 或 plan 中给出了参考文本，还是完全由实现自由决定？ [Clarity, Spec §FR-003]

- [x] CHK012 - 单轮多工具调用中部分工具失败时（其余工具成功），框架行为是否在 spec Edge Cases 中有明确表述（成功结果仍正常返回，失败结果作为错误观察返回）？ [Completeness, Spec §Edge Cases]

- [x] CHK013 - 系统提示极长导致接近上下文限制时，"框架应记录警告"中的警告机制是否已明确定义（通过 `on_error` 事件？通过 Python 日志？还是其他途径）？ [Clarity, Spec §Edge Cases]

- [x] CHK014 - LLM API 失败（SDK `max_retries=3` 全部耗尽后）时，框架向调用方抛出的异常类型是否在 contracts/public-api.md §6 中明确标注（`openai.APIError` 子类）？ [Clarity, Spec §6]

- [x] CHK015 - "LLM 返回无效 JSON tool_call → 触发 `on_error` + 作为 tool 结果返回循环继续"这一行为是否在 spec FR-013 和 contracts/public-api.md §6 中表述一致，且 `on_error` 的 `data` 载荷所包含字段已明确？ [Consistency, Spec §FR-013 / §6]

---

## 三、测试规范可验证性

- [x] CHK016 - spec FR-018 中列出的 7 个核心模块是否与 plan.md 中规划的 7 个测试文件（`test_schemas.py` ~ `test_agent.py`）一一对应，无遗漏？ [Consistency, Spec §FR-018]

- [x] CHK017 - FR-018 要求"每个公共方法至少覆盖一个错误/边界场景"这一标准是否在 spec 中明文写出，还是仅在宪法原则 X 中存在？若仅在宪法中，spec FR-018 是否应引用宪法 X？ [Completeness, Spec §FR-018]

- [x] CHK018 - SC-006"核心模块单元测试可在无真实 API 密钥的环境中全部通过"中的"核心模块"范围是否与 FR-018 中的 7 个模块定义对齐，无歧义？ [Consistency, Spec §SC-006 / §FR-018]

- [x] CHK019 - SC-004（并发 10 个独立会话验证无历史交叉）的验收标准是否可在无真实 API 密钥的环境中通过 mock 验证，还是必须依赖集成测试？若需集成测试，是否应在 spec 中明示？ [Measurability, Spec §SC-004]

- [x] CHK020 - `RUN_INTEGRATION_TESTS=1` 环境变量作为集成测试门控是否在 spec §5（环境变量配置表）和 contracts/public-api.md §5 中均有记载，确保文档一致？ [Consistency, Spec §5]

---

## 四、回调事件契约完整性

- [x] CHK021 - 7 类生命周期事件中，每类事件的 `data` 载荷字段是否均在 spec FR-014 或 contracts/public-api.md §4 中完整枚举（当前 §4 仅有 `on_tool_start` 和 `on_tool_end` 示例）？ [Completeness, Spec §FR-014]

- [x] CHK022 - 多个 `BaseCallbackHandler` 同时注册时的执行顺序是否在 spec 或 contracts 中有明确定义（按注册顺序？还是无序？）？ [Coverage, Gap]

- [x] CHK023 - 回调方法抛出异常时框架的隔离行为（不影响主流程、后续回调仍继续执行）是否在 spec FR-013 中有明确表述？ [Completeness, Spec §FR-013]

- [x] CHK024 - `ConsoleCallbackHandler` 的输出格式是否有任何规范性要求（字段顺序、时间戳格式、颜色等），还是完全由实现自由定义？若为自由实现，是否应在 spec FR-015 中明确注明？ [Clarity, Spec §FR-015]

- [x] CHK025 - 流式模式（`run_stream()`）下 `on_llm_end` 在流结束后触发一次并携带完整内容这一行为是否在 spec FR-013 中明文表述，且与 contracts/public-api.md §2.3 的流式行为描述一致？ [Consistency, Spec §FR-013]

---

## 五、上下文管理边界定义

- [x] CHK026 - `keep_last_n` 中的"轮"是否在 spec FR-006 中有精确定义（一轮 = 一条 user 消息 + 一条 assistant 回复，是否含该轮产生的 tool 消息对）？ [Clarity, Spec §FR-006]

- [x] CHK027 - `max_messages`（默认 20）与 `keep_last_n`（默认 6 轮）两个参数并存时的截断优先级是否在 spec FR-006 中明确（哪个约束先生效？两者是否可能冲突）？ [Clarity, Spec §FR-006]

- [x] CHK028 - 单轮产生 N 个工具调用（1 + N 条原子消息）且这些消息总数已超过 `max_messages` 限制时，框架行为是否在 spec 中有定义（强制保留原子对，还是报错）？ [Coverage, Edge Case, Spec §FR-006]

- [x] CHK029 - FR-007（系统提示永远不被截断）与极端情况（系统提示本身已超过 `max_messages`）的冲突是否在 spec 中有处理方案描述？ [Coverage, Edge Case, Spec §FR-007]

---

## 六、阶段预留接口文档质量

- [x] CHK030 - `list[ContentPart]` 路径抛出 `NotImplementedError` 的错误消息文本是否在 spec FR-020 中有参考描述，使其对未来开发者具有足够指引性？ [Clarity, Spec §FR-020]

- [x] CHK031 - `NextStep.HANDOFF` 和 `NextStep.INTERRUPT` 在 Phase 1 的"占位实现"行为是否在 spec FR-021 中有明确定义（抛出 `NotImplementedError`？静默忽略？返回 `STOP`？）？ [Completeness, Spec §FR-021]

- [x] CHK032 - `is_destructive` 和 `permission` 两个属性的语义关系是否在 spec FR-022 中有明确说明（冗余备选？互补约束？优先级关系？），避免 Phase 4 实现时出现歧义？ [Clarity, Spec §FR-022]

- [x] CHK033 - Phase 1 中 `permission="write"` 工具的行为是否在 spec 中明确（与 `permission="read"` 完全相同，门控逻辑在 Phase 4 激活），确保使用者不会对 Phase 1 的 write 权限有错误预期？ [Completeness, Spec §FR-022 / Out of Scope]

---

## Notes

- 打勾前须确认对应需求文字已在 spec/plan/contracts 中存在且清晰，而非仅在实现代码中体现
- 若某条目答案为"否"，应在对应文档中补充描述后再打勾
- 标注 `[Gap]` 的条目表示需求文档中当前存在空白，优先处理
- 所有条目通过后，Phase 1 可正式进入收尾和 Phase 2 规划
