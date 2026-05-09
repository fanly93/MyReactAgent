"""
示例 01：基础工具调用
Phase 1 MVP 完成标志示例，展示 ReAct 循环的完整流程。

运行方式：
    python examples/01_basic_tool_use.py

需要环境变量：
    OPENAI_API_KEY=...
    OPENAI_MODEL=gpt-4o-mini  (可选，默认 gpt-4o-mini)
    OPENAI_BASE_URL=...        (可选，用于兼容其他 OpenAI 协议服务商)
"""

from myreactagent import ReactAgent, BaseTool, tool, ToolResult, ConsoleCallbackHandler


# ── 方式一：@tool 装饰器（适合简单函数）──────────────────────────────────────────

@tool
def calculate(expression: str) -> str:
    """计算 Python 数学表达式并返回结果。支持加减乘除和括号。"""
    try:
        # 只允许安全的数学表达式
        allowed = set("0123456789+-*/()., ")
        if not all(c in allowed for c in expression):
            return f"错误：表达式含有不允许的字符"
        result = eval(expression)  # noqa: S307
        return str(result)
    except Exception as e:
        return f"计算错误：{e}"


@tool
def get_current_date() -> str:
    """返回今天的日期（格式：YYYY-MM-DD）。"""
    from datetime import date
    return str(date.today())


# ── 方式二：类继承（适合复杂工具）────────────────────────────────────────────────

class UnitConverterTool(BaseTool):
    """单位换算工具：支持摄氏/华氏温度、千米/英里转换。"""

    name = "unit_converter"
    description = "单位换算工具，支持温度（摄氏转华氏）和距离（千米转英里）。"
    is_destructive = False
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "value": {"type": "number", "description": "要换算的数值"},
                "conversion": {
                    "type": "string",
                    "description": "换算类型：'celsius_to_fahrenheit' 或 'km_to_miles'",
                    "enum": ["celsius_to_fahrenheit", "km_to_miles"],
                },
            },
            "required": ["value", "conversion"],
        }

    def execute(self, args: dict) -> ToolResult:
        value = args["value"]
        conversion = args["conversion"]
        if conversion == "celsius_to_fahrenheit":
            result = value * 9 / 5 + 32
            return ToolResult(
                tool_call_id="",
                success=True,
                content=f"{value}°C = {result:.1f}°F",
            )
        elif conversion == "km_to_miles":
            result = value * 0.621371
            return ToolResult(
                tool_call_id="",
                success=True,
                content=f"{value} 千米 = {result:.2f} 英里",
            )
        return ToolResult(tool_call_id="", success=False, error=f"不支持的换算类型：{conversion}")


def demo_basic_tool_call():
    """演示 1：基础工具调用（算术计算）。"""
    print("\n" + "=" * 60)
    print("演示 1：基础工具调用")
    print("=" * 60)

    agent = ReactAgent(
        tools=[calculate],
        system_prompt="你是一个数学助手，使用 calculate 工具来完成计算任务。",
        callbacks=[ConsoleCallbackHandler()],
        max_iterations=5,
    )

    result = agent.run("(123 + 456) × 7 等于多少？请用 calculate 工具计算。")
    print(f"\n最终答案：{result}\n")


def demo_multi_tool():
    """演示 2：多工具混合使用（装饰器工具 + 类继承工具）。"""
    print("\n" + "=" * 60)
    print("演示 2：多工具混合使用")
    print("=" * 60)

    agent = ReactAgent(
        tools=[calculate, get_current_date, UnitConverterTool()],
        system_prompt="你是一个多功能助手，可以计算数学、查询日期、进行单位换算。",
        callbacks=[ConsoleCallbackHandler()],
        max_iterations=8,
    )

    result = agent.run("今天是哪天？另外，25 摄氏度等于多少华氏度？请分别回答。")
    print(f"\n最终答案：{result}\n")


def demo_multi_turn():
    """演示 3：多轮对话（同一 Agent 实例复用，历史自动保留）。"""
    print("\n" + "=" * 60)
    print("演示 3：多轮对话")
    print("=" * 60)

    agent = ReactAgent(
        tools=[calculate],
        system_prompt="你是一个友好的助手，记住用户告诉你的信息。",
        max_iterations=3,
    )

    # 第一轮：告知信息
    r1 = agent.run("我的名字是张三，我最喜欢的数字是 42。")
    print(f"第一轮回答：{r1}")

    # 第二轮：测试记忆
    r2 = agent.run("我叫什么名字？我最喜欢的数字是什么？")
    print(f"第二轮回答：{r2}")


def demo_streaming():
    """演示 4：流式输出（逐 token 打印）。"""
    print("\n" + "=" * 60)
    print("演示 4：流式输出")
    print("=" * 60)

    agent = ReactAgent(
        tools=[calculate],
        system_prompt="你是一个助手，用简短的语言回答问题。",
        max_iterations=5,
    )

    print("流式输出：", end="", flush=True)
    for token in agent.run_stream("先计算 7 乘以 8，然后用一句话告诉我结果。"):
        print(token, end="", flush=True)
    print("\n")


if __name__ == "__main__":
    import os

    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠️  请先设置 OPENAI_API_KEY 环境变量")
        print("   export OPENAI_API_KEY=your-key-here")
        exit(1)

    print("🚀 MyReactAgent Phase 1 MVP 演示")
    print(f"   模型：{os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')}")

    demo_basic_tool_call()
    demo_multi_tool()
    demo_multi_turn()
    demo_streaming()

    print("\n✅ Phase 1 MVP 演示完成！")
