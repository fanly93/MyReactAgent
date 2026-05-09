# 快速开始: MyReactAgent Phase 1

**Feature**: `001-phase1-mvp-prototype`  
**生成时间**: 2026-05-08

---

## 环境准备

```bash
# 安装依赖
pip install openai pydantic

# 设置环境变量
export OPENAI_API_KEY="your-api-key"
export OPENAI_MODEL="gpt-4o-mini"          # 可选，默认 gpt-4o-mini
# export OPENAI_BASE_URL="..."             # 使用其他兼容提供商时设置
```

---

## 15 行最小示例（SC-001 验证）

```python
from myreactagent import ReactAgent
from myreactagent.tools import tool

@tool
def add(a: int, b: int) -> int:
    """将两个整数相加。"""
    return a + b

@tool
def multiply(a: int, b: int) -> int:
    """将两个整数相乘。"""
    return a * b

agent = ReactAgent(tools=[add, multiply], system_prompt="你是一个数学助手，使用工具来计算结果。")
answer = agent.run("3 乘以 7 加上 8 等于多少？")
print(answer)
```

预期输出：
```
3 乘以 7 加上 8 等于 29。
```

---

## 完整示例（对应 examples/01_basic_tool_use.py）

```python
import os
from myreactagent import ReactAgent
from myreactagent.tools import tool, BaseTool, ToolResult
from myreactagent.callbacks import ConsoleCallbackHandler

# ── 1. 用装饰器定义简单工具 ──────────────────────────────────

@tool
def add(a: int, b: int) -> int:
    """将两个整数相加并返回结果。"""
    return a + b

@tool
def multiply(a: int, b: int) -> int:
    """将两个整数相乘并返回结果。"""
    return a * b

@tool
def get_current_time() -> str:
    """获取当前时间，格式为 HH:MM:SS。"""
    from datetime import datetime
    return datetime.now().strftime("%H:%M:%S")

# ── 2. 用类继承定义复杂工具 ──────────────────────────────────

class WeatherTool(BaseTool):
    name = "get_weather"
    description = "查询指定城市的当前天气信息。"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称，如'北京'、'上海'"},
            },
            "required": ["city"],
        }

    def execute(self, args: dict) -> ToolResult:
        city = args["city"]
        # 模拟天气数据
        return ToolResult(
            tool_call_id=args.get("_tool_call_id", ""),
            success=True,
            content=f"{city}当前晴天，气温 22°C，湿度 60%。",
        )

# ── 3. 创建 Agent ─────────────────────────────────────────────

agent = ReactAgent(
    tools=[add, multiply, get_current_time, WeatherTool()],
    system_prompt="你是一个智能助手，会使用工具来完成数学计算和信息查询任务。",
    callbacks=[ConsoleCallbackHandler()],  # 打印执行过程
    max_iterations=10,
)

# ── 4. 多步骤工具调用 ─────────────────────────────────────────

print("=== 示例 1：多步骤数学计算 ===")
answer = agent.run("先计算 3 乘以 7，然后把结果加上 8，最终答案是多少？")
print(f"\n最终答案: {answer}\n")

# ── 5. 多轮对话 ───────────────────────────────────────────────

print("=== 示例 2：多轮对话上下文保持 ===")
agent.run("我最喜欢的城市是成都。")
answer = agent.run("查询一下我最喜欢的城市的天气，然后告诉我现在几点了。")
print(f"\n最终答案: {answer}\n")

# ── 6. 流式输出 ───────────────────────────────────────────────

print("=== 示例 3：流式输出 ===")
print("流式输出: ", end="")
for token in agent.run_stream("用一句话总结一下 ReAct Agent 的工作原理。"):
    print(token, end="", flush=True)
print("\n")
```

---

## 工具异常处理示例

```python
@tool
def safe_divide(a: float, b: float) -> float:
    """将 a 除以 b。"""
    return a / b  # b=0 时抛出 ZeroDivisionError

agent = ReactAgent(tools=[safe_divide])
# Agent 会收到错误作为观察，尝试修正后继续
answer = agent.run("计算 10 除以 0 的结果。")
# Agent 观察到错误，自主给出解释
```

---

## 自定义回调示例

```python
from myreactagent.callbacks import BaseCallbackHandler
from myreactagent.schemas import CallbackEvent
import json

class JsonLogger(BaseCallbackHandler):
    """将所有事件以 JSON 格式写入日志文件。"""

    def __init__(self, log_file: str):
        self.log_file = log_file

    def _write(self, event: CallbackEvent) -> None:
        with open(self.log_file, "a") as f:
            f.write(json.dumps(event.model_dump()) + "\n")

    def on_agent_start(self, event: CallbackEvent) -> None:
        self._write(event)

    def on_llm_end(self, event: CallbackEvent) -> None:
        self._write(event)

    def on_tool_end(self, event: CallbackEvent) -> None:
        self._write(event)

    def on_agent_end(self, event: CallbackEvent) -> None:
        self._write(event)

    def on_error(self, event: CallbackEvent) -> None:
        self._write(event)

agent = ReactAgent(
    tools=[add, multiply],
    callbacks=[JsonLogger("agent_events.jsonl")],
)
agent.run("3 加 5 等于多少？")
```

---

## 会话隔离示例

```python
# 两个完全独立的会话，互不干扰
agent_a = ReactAgent(tools=[add])
agent_b = ReactAgent(tools=[multiply])

agent_a.run("我叫小明。")
agent_b.run("我叫小红。")

# 两个 Agent 的历史完全独立
print(agent_a.run("我叫什么名字？"))  # "你叫小明。"
print(agent_b.run("我叫什么名字？"))  # "你叫小红。"
```

---

## 运行测试

```bash
# 单元测试（无需 API Key）
pytest tests/ -v

# 集成测试（需要真实 API Key）
RUN_INTEGRATION_TESTS=1 pytest tests/ -v -m integration
```
