# MyReactAgent 演示套件

本目录包含 Phase 1 全功能演示，通过真实 API 调用验证所有核心需求点。

---

## 快速开始

### 第一步：安装演示依赖

```bash
# 在项目根目录执行
uv pip install -r demos/requirements.txt
```

### 第二步：填写 API Key

复制模板并填入你的 API Key：

```bash
cp demos/.env.example demos/.env
# 然后编辑 demos/.env，填入实际 Key
```

`.env` 中至少填写一个模型提供商的 Key，演示才能正常运行。

### 第三步：运行演示

```bash
# 一键运行 Phase 1 全部演示
python demos/phase1/run_all.py

# 运行单个演示
python demos/phase1/01_basic_react_loop.py

# 只运行指定演示（如 01 和 03）
python demos/phase1/run_all.py 01 03

# 跳过多提供商对比演示（只有一个 Key 时可用）
python demos/phase1/run_all.py --skip 06
```

---

## 演示列表

| 文件 | 内容 | 验证功能点 |
|------|------|-----------|
| `phase1/01_basic_react_loop.py` | 基础 ReAct 循环 | FR-001 ~ FR-003, SC-001 ~ SC-003 |
| `phase1/02_multi_turn_memory.py` | 多轮对话上下文保持 | US2, FR-005 ~ FR-007, SC-004 |
| `phase1/03_streaming.py` | 实时流式输出 | US3, FR-004 |
| `phase1/04_callbacks.py` | 执行过程可观测性 | US4, SC-005, FR-013 ~ FR-015 |
| `phase1/05_tools_advanced.py` | 真实工具集成 | FR-008 ~ FR-012 |
| `phase1/06_multi_provider.py` | 多模型提供商横向对比 | 全部提供商 |

---

## 提供商配置

| 提供商 | 环境变量 | 模型 |
|--------|---------|------|
| 🟢 OpenAI | `OPENAI_API_KEY` | gpt-4o-mini |
| 🔵 DeepSeek | `DEEPSEEK_API_KEY` | deepseek-chat |
| 🟠 DashScope (通义千问) | `DASHSCOPE_API_KEY` | qwen-plus |
| 🔴 Gemini | `GEMINI_API_KEY` | gemini-2.0-flash |
| 🟣 Anthropic | `ANTHROPIC_API_KEY` | claude-3-5-haiku-20241022 |

演示会自动检测已配置的提供商，未配置的将跳过。

---

## 工具 API Key

| 工具 | 环境变量 | 说明 |
|------|---------|------|
| Tavily 联网搜索 | `TAVILY_API_KEY` | 需注册 [tavily.com](https://tavily.com) |
| OpenWeatherMap 天气 | `OPENWEATHERMAP_API_KEY` | 需注册 [openweathermap.org](https://openweathermap.org) |
| wttr.in 天气 | 无需 Key | 免费公共 API |

---

## 演示 05 工具说明

`05_tools_advanced.py` 集成了以下真实工具：

- **TavilySearchTool** — 联网搜索最新信息（需 `TAVILY_API_KEY`）
- **WttrWeatherTool** — 实时天气查询，完全免费，无需 Key
- **OpenWeatherTool** — OpenWeatherMap 天气（需 `OPENWEATHERMAP_API_KEY`）
- **calculator** — 安全数学计算（内置，无需网络）
- **get_current_datetime** — 获取当前时间（内置，无需网络）

没有工具 API Key 时，演示 05 仍会运行内置工具部分。

---

## 目录结构

```
demos/
├── .env                  # 你的 API Key（不提交到 git）
├── .env.example          # API Key 模板
├── requirements.txt      # 演示额外依赖
├── _utils.py             # 共享工具函数和提供商配置
├── _anthropic_adapter.py # Anthropic 原生 SDK 适配器
├── README.md             # 本文件
└── phase1/
    ├── run_all.py        # 一键运行入口
    ├── 01_basic_react_loop.py
    ├── 02_multi_turn_memory.py
    ├── 03_streaming.py
    ├── 04_callbacks.py
    ├── 05_tools_advanced.py
    └── 06_multi_provider.py
```
