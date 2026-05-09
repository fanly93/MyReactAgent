# MyReactAgent — 项目说明

## 语言规范

**所有回答和文档必须使用中文。** 禁止使用英文、韩文、日文或其他语言回答用户问题。代码中的变量名、函数名、注释遵循以下规则：
- 变量名、函数名、类名：使用英文（符合 Python 命名规范）
- 代码注释：使用中文
- 文档（Markdown）：全部使用中文
- 错误信息和日志：使用英文（便于国际化和调试）

---

## 项目定位

**MyReactAgent** 是一个从零开始、纯手工实现的 ReAct Agent 框架，目标是对标 LangChain / LangGraph / OpenAI Agents SDK 等主流框架。

**核心约束**：
- 只允许使用 `openai` SDK 等基础模型调用库
- **禁止**使用任何 Agent 框架库（LangChain、LangGraph、agents-python、Google ADK、AutoGen、CrewAI 等）
- 支持所有兼容 OpenAI 协议的 LLM 提供商（只需修改 `base_url`）

**双重目标**：
1. **学习**：通过手动实现理解 Agent 框架底层机制，代码可读性优先
2. **生产**：最终产出可投入实际项目使用的框架，Phase 4 对标主流框架能力

---

## 技术栈

| 类别 | 选型 |
|------|------|
| 编程语言 | Python 3.11+ |
| LLM 调用 | `openai` SDK（兼容所有 OpenAI 协议提供商） |
| 数据验证 | `pydantic` v2 |
| 向量存储 | `chromadb`（默认）/ `faiss-cpu`（可选） |
| 异步框架 | `asyncio`（Phase 2 起引入） |
| Web 服务 | `FastAPI`（Phase 4 引入） |
| 测试框架 | `pytest` + `pytest-mock` |

---

## 分阶段实现计划

### Phase 1 — MVP：单 Agent + 工具调用（同步）

**目标**：跑通核心 ReAct 循环，代码清晰可读

**完成标志**：`examples/01_basic_tool_use.py` 端到端运行成功

### Phase 2 — 流式响应 + 多 Agent（引入 async）

**目标**：支持实时流式输出，实现层级式多 Agent 编排

**完成标志**：`examples/03_streaming_agent.py` + `examples/04_multi_agent.py` 通过

### Phase 3 — 长短期记忆

**目标**：支持对话历史管理和跨会话语义检索

**完成标志**：`examples/02_memory_agent.py` 展示跨会话记忆召回

### Phase 4 — 生产级（对标 LangChain / OpenAI Agents）

**目标**：完整生产能力，前后端分离，支持 MCP 和 Skill 生态

新增能力：
- **可观测性**：`BaseCallbackHandler` 系统 + `OpenTelemetryCallbackHandler`
- **Human-in-the-Loop**：`is_destructive` 工具标记 + 暂停/恢复状态持久化
- **重试与降级**：指数退避重试 + fallback 模型链 + 熔断器
- **上下文压缩**：基于 LLM 的历史摘要策略
- **MCP 支持**：`MCPToolLoader` 接入任意 MCP Server
- **Skill 系统**：标准化 Skill 打包格式，支持社区共享
- **Web 服务层**：FastAPI + SSE 流式接口 + REST 接口
- **多模态输入**：图像、音频等非文本内容的工具调用与消息传递支持

---

## 项目宪法

完整的 17 条宪法原则见 `.specify/memory/constitution.md`。

**宪法摘要（开发时须遵守）**：
1. 可读性优先，分阶段质量标准
2. 最小化依赖，每个依赖需有充分理由
3. 显式优于隐式，禁止魔法行为
4. 层次边界不可越界（utils → tools → llm/memory → agent → server）
5. 接口从第一阶段预留，实现逐阶段递进
6. Callback Hook 可观测性，核心代码不含 trace 逻辑
7. 统一事件格式，SSE 优先对接前端
8. Phase 1 同步，Phase 2 起引入 async
9. 自动重试 + 降级，生产环境不允许程序崩溃
10. 每个核心模块必须有对应测试
11. Human-in-the-Loop：不可逆操作需人工确认
12. 会话状态完全隔离，零全局可变状态
13. 框架内置上下文窗口管理，不甩给用户
14. 工具参数和 Agent 输出统一走 Pydantic 验证
15. 安全边界：Prompt Injection 防护 + 工具权限分级
16. 生态兼容：MCP 协议 + Skill 打包 + 多模态输入（Phase 1 预留 Union schema，Phase 4 实现）
17. ReAct 循环终止规范：主终止信号 / 安全兜底 / NextStep 枚举模式

---

## 开发规范

### 运行测试

```bash
# 单元测试（无需真实 API）
pytest tests/ -v

# 集成测试（需要真实 API Key）
RUN_INTEGRATION_TESTS=1 pytest tests/ -v -m integration
```

### 运行示例

```bash
# Phase 1
python examples/01_basic_tool_use.py

# Phase 2
python examples/03_streaming_agent.py
python examples/04_multi_agent.py

# Phase 3
python examples/02_memory_agent.py
```

### 环境变量

```bash
OPENAI_API_KEY=...          # OpenAI API Key
OPENAI_BASE_URL=...         # 可选：覆盖为其他 OpenAI 兼容提供商
OPENAI_MODEL=gpt-4o-mini    # 默认模型
RUN_INTEGRATION_TESTS=1     # 启用集成测试
```

---

## 阶段启动规范

开始新阶段前，MUST 先阅读 `specs/deferred-items.md`。

---

<!-- SPECKIT START -->
## 当前功能计划

**功能**: Phase 1 MVP — ReAct Agent 核心框架  
**分支**: `001-phase1-mvp-prototype`  
**计划文档**: `specs/001-phase1-mvp-prototype/plan.md`  
**规范文档**: `specs/001-phase1-mvp-prototype/spec.md`
<!-- SPECKIT END -->
