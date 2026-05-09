# 跨阶段延迟项注册表

> **读取规范**：开始新阶段的 `/speckit-specify` 之前，MUST 先读此文件，将本阶段应实现的延迟项纳入新阶段 spec。  
> 代码层路标：各延迟点在实现代码中以 `# TODO Phase N:` 注释标注，指向本文件。

---

## Phase 3 待实现项

### DI-001 — 工具输出 token-aware 截断

**来源**：Phase 1 FR-006b（`specs/001-phase1-mvp-prototype/spec.md`）  
**代码位置**：`myreactagent/tools/registry.py` → `execute()` 返回前  
**当前实现**：对工具返回的 `content` 字符串按 `MAX_TOOL_OUTPUT_CHARS=8000` 做字符级截断，截断时附加提示语通知模型内容已被截断。字符数是 token 数的粗近似（中文场景误差约 2-3 倍）。  
**Phase 3 目标**：
1. 使用 `tiktoken` 对工具输出做精确 token 计数，超出阈值时截断
2. 阈值改为可配置参数（全局默认 + 工具级覆盖 `BaseTool.max_output_tokens`）
3. 截断策略可选：头部保留（默认）/ 尾部保留 / 中间摘要（LLM 压缩）
4. 参考实现：hermes-agent `context_compressor.py`

---

### DI-002 — 上下文窗口 token-aware 截断

**来源**：Phase 1 FR-006（`specs/001-phase1-mvp-prototype/spec.md`）  
**代码位置**：`myreactagent/memory/conversation.py` → `_truncate()`  
**当前实现**：以消息条数（`max_messages`）为截断单位，字符数近似。宪法 XIII 明确注明"Phase 1–2 acceptable"。  
**Phase 3 目标**：
1. 引入 `tiktoken` 对每条消息做精确 token 计数
2. `max_messages` 保留（向后兼容），新增 `max_tokens` 参数，两者均触发截断时取先满足者
3. 新增 `summarize` 策略：对保护区外的中间消息调用 LLM 生成摘要替代原始消息（增量摘要，见宪法 XIII）
4. 参考实现：ADK `compaction.py`、hermes-agent `context_compressor.py`

---

### DI-003 — on_tool_error 独立事件（可选）

**来源**：Phase 1 设计决策（工具异常走 `on_tool_end(success=False)`，非 `on_error`）  
**代码位置**：`myreactagent/agent/react.py` → `_run_tool_calls()`  
**当前实现**：工具执行异常通过 `ToolResult(success=False)` + `on_tool_end` 上报，与成功路径共用同一事件。  
**Phase 2/3 目标**（可选评估）：
- 评估是否需要新增 `on_tool_error` 独立事件，以便调用方不需要检查 `success` 字段即可区分成功/失败路径
- 决策依据：Phase 2 多 Agent 场景下，Orchestrator 是否需要单独监听子 Agent 的工具失败

---

## Phase 4 待实现项

### DI-004 — 工具权限门控（HITL）

**来源**：Phase 1 FR-022（`specs/001-phase1-mvp-prototype/spec.md`）  
**代码位置**：`myreactagent/tools/base.py` → `is_destructive`、`permission` 属性  
**当前实现**：`BaseTool` 声明了 `is_destructive: bool` 和 `permission` 属性，Phase 1 不实现门控逻辑（宪法 XI 豁免）。  
**Phase 4 目标**：
1. `is_destructive=True` 时触发 `approval_required` 事件，暂停循环等待人工确认
2. 未注册 HITL 处理器时抛出 `MissingHITLHandlerError`（开发模式可通过 `safe_mode=False` 绕过）
3. 会话状态可序列化为 JSON，支持跨进程重启后从中断点恢复（以 `thread_id` 为恢复凭证）
4. 参考实现：宪法原则 XI、LangGraph `Interrupt + Checkpointer`

---

### DI-005 — OpenTelemetry span_id 填充

**来源**：Phase 1 FR-014（`specs/001-phase1-mvp-prototype/spec.md`）  
**代码位置**：`myreactagent/schemas/events.py` → `CallbackEvent.span_id`  
**当前实现**：`span_id` 始终为空字符串，Schema 已预留字段。  
**Phase 4 目标**：接入 OpenTelemetry SDK，在 `_emit()` 时填充当前 span 的 `span_id`，实现分布式追踪。

---

### DI-006 — NextStep.HANDOFF / INTERRUPT 完整实现

**来源**：Phase 1 FR-021（`specs/001-phase1-mvp-prototype/spec.md`）  
**代码位置**：`myreactagent/agent/react.py` → `run()` 循环中 `next_step` 判断处（枚举定义在 `myreactagent/schemas/events.py`）  
**当前实现**：`HANDOFF` 和 `INTERRUPT` 枚举值已定义；`run()` 循环中遇到这两种状态时抛出 `NotImplementedError`，错误消息标明目标阶段。  
**Phase 2 目标**（HANDOFF）：实现子 Agent 移交控制权机制（OrchestratorAgent）  
**Phase 4 目标**（INTERRUPT）：与 DI-004 HITL 联动实现人工中断与恢复

---

## 变更日志

| 日期 | 版本 | 变更 |
|------|------|------|
| 2026-05-09 | v1.0 | 初始创建，收录 Phase 1 产生的 6 项延迟条目 |
