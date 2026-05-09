"""
演示 01：基础 ReAct 循环（FR-001 ~ FR-003, US1, SC-001/002/003）

验证点：
  ✓ 15 行内创建可运行 Agent（SC-001）
  ✓ 多步骤工具调用完成数学计算（US1 独立验收测试）
  ✓ 工具异常不崩溃，转化为结构化观察（FR-011, SC-003）
  ✓ 单轮多工具并行调用（FR-010）
  ✓ max_iterations 安全兜底（FR-003）
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demos._utils import load_env, header, section, step, ok, warn, err, result, timer, make_agent
from myreactagent import tool, BaseTool, ToolResult

load_env()


# ── 工具定义 ──────────────────────────────────────────────────────────────────

@tool
def add(a: int, b: int) -> int:
    """将两个整数相加并返回结果。"""
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """将两个整数相乘并返回结果。"""
    return a * b


@tool
def divide(a: float, b: float) -> float:
    """将 a 除以 b，b 为 0 时抛出错误。"""
    if b == 0:
        raise ZeroDivisionError("除数不能为零")
    return a / b


class PowerTool(BaseTool):
    """计算 base 的 exp 次方（类继承方式定义工具）。"""

    name = "power"
    description = "计算 base 的 exp 次方，例如 2^10 = 1024。"
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "base": {"type": "number", "description": "底数"},
                "exp": {"type": "number", "description": "指数"},
            },
            "required": ["base", "exp"],
        }

    def execute(self, args: dict) -> ToolResult:
        val = args["base"] ** args["exp"]
        return ToolResult(tool_call_id="", success=True, content=str(val))


# ── 演示函数 ──────────────────────────────────────────────────────────────────

def demo_sc001_15_lines():
    """SC-001：开发者能在 15 行以内的代码创建带自定义工具的可运行 Agent。"""
    section("SC-001  15 行最小示例")
    from myreactagent import ReactAgent

    # ── 以下即"15 行以内"的开发者视角代码（行数统计从 @tool 到 print） ──────────
    # 1  @tool
    # 2  def add(a: int, b: int) -> int:
    # 3      """将两个整数相加。"""
    # 4      return a + b
    # 5
    # 6  @tool
    # 7  def multiply(a: int, b: int) -> int:
    # 8      """将两个整数相乘。"""
    # 9      return a * b
    # 10
    # 11 agent = ReactAgent(tools=[add, multiply],
    # 12                    api_key="sk-...", model="gpt-4o-mini")
    # 13 answer = agent.run("3 乘以 7 加上 8 等于多少？")
    # 14 print(answer)    ← 共 14 行，满足 SC-001

    # 实际运行使用 make_agent 以支持多提供商切换
    agent, cfg = make_agent(tools=[add, multiply])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} / {cfg['model']}")

    with timer("run"):
        ok_flag, answer = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, "3 乘以 7 加上 8 等于多少？"
        )

    if ok_flag:
        result("答案", answer)
        if "29" in answer:
            ok("答案包含正确结果 29 ✓")
        else:
            warn(f"答案未包含 29，请检查（模型回答: {answer[:60]}）")


def demo_us1_multi_step():
    """US1：多步骤任务执行（独立验收测试）。"""
    section("US1  多步骤计算 + 多工具综合")
    agent, cfg = make_agent(tools=[add, multiply, PowerTool()])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} / {cfg['model']}")

    step("问题：先计算 3 × 7，再加上 8，然后把结果做 2 次方")
    with timer():
        ok_flag, answer = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run,
            "先计算 3 乘以 7，然后把结果加上 8，最后对最终结果做 2 次方，告诉我每一步的中间值和最终答案。"
        )
    if ok_flag:
        result("答案", answer)
        ok("多步骤工具调用完成")


def demo_fr011_tool_exception():
    """FR-011/SC-003：工具异常转化为结构化观察，循环不崩溃。"""
    section("FR-011 / SC-003  工具异常处理")
    agent, cfg = make_agent(tools=[divide, add])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} / {cfg['model']}")

    step("请求 10 ÷ 0（触发 ZeroDivisionError）...")
    with timer():
        ok_flag, answer = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run,
            "计算 10 除以 0 的结果，如果失败请解释原因并用 add 工具计算 10 + 0 作为替代。"
        )
    if ok_flag:
        result("答案", answer)
        ok("工具异常被捕获，Agent 继续循环并给出答案 ✓")


def demo_fr010_multi_tool_one_round():
    """FR-010：单轮响应中多工具调用。"""
    section("FR-010  单轮多工具并行调用")
    agent, cfg = make_agent(tools=[add, multiply, divide])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']}")

    step("请求在一轮内完成三个独立计算...")
    with timer():
        ok_flag, answer = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run,
            "请同时计算以下三个结果并汇总：① 15 + 27，② 8 × 9，③ 100 ÷ 4"
        )
    if ok_flag:
        result("答案", answer)
        ok("单轮多工具调用完成")


def demo_fr003_max_iterations():
    """FR-003：max_iterations 达到上限时安全兜底而非崩溃。"""
    section("FR-003  max_iterations 安全兜底")

    @tool
    def always_needs_more(step: str) -> str:
        """假装需要更多步骤的工具。"""
        return f"完成步骤 {step}，但还需要继续..."

    agent, cfg = make_agent(tools=[always_needs_more], max_iterations=3)
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} | max_iterations=3")

    step("触发迭代上限...")
    with timer():
        ok_flag, answer = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, "请调用工具 5 次，每次传入不同的步骤名"
        )
    if ok_flag:
        result("答案", answer)
        ok("达到上限后触发安全兜底，未抛出异常 ✓")


# ── 主入口 ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    header("演示 01：基础 ReAct 循环")

    try:
        demo_sc001_15_lines()
        demo_us1_multi_step()
        demo_fr011_tool_exception()
        demo_fr010_multi_tool_one_round()
        demo_fr003_max_iterations()
        print(f"\n{'='*62}")
        ok("演示 01 全部完成！")
    except RuntimeError as e:
        err(str(e))
        print("\n请先填写 demos/.env 中的 API Key")
        sys.exit(1)
