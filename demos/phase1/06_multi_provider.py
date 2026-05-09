"""
演示 06：多模型提供商横向对比

对同一问题用所有已配置的提供商分别运行，比较：
  - 响应质量
  - 工具调用准确性
  - 首字延迟 & 总耗时
  - 流式输出体验

支持的提供商（需在 demos/.env 中配置对应 API Key）：
  🟢 OpenAI    (gpt-4o-mini)
  🔵 DeepSeek  (deepseek-chat)
  🟠 DashScope (qwen-plus)
  🔴 Gemini    (gemini-2.0-flash)
  🟣 Anthropic (claude-3-5-haiku，原生 SDK 适配)
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demos._utils import (load_env, header, section, step, ok, warn, err,
                           result, timer, make_agent, list_available_providers,
                           get_provider_config, C)
from myreactagent import tool

load_env()


# ── 测试工具 ──────────────────────────────────────────────────────────────────

@tool
def add(a: int, b: int) -> int:
    """将两个整数相加。"""
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """将两个整数相乘。"""
    return a * b


@tool
def fibonacci(n: int) -> int:
    """计算斐波那契数列第 n 项（从 0 开始）。"""
    if n <= 0:
        return 0
    if n == 1:
        return 1
    a, b = 0, 1
    for _ in range(2, n + 1):
        a, b = b, a + b
    return b


# ── 测试用例 ──────────────────────────────────────────────────────────────────

TEST_CASES = [
    {
        "name": "基础数学（SC-001 场景）",
        "prompt": "计算 3 乘以 7 再加上 8，最终答案是多少？",
        "tools": [add, multiply],
        "check": lambda r: "29" in (r or ""),
        "expected": "包含 29",
    },
    {
        "name": "多步骤工具链",
        "prompt": "先计算 fibonacci(10)，再把结果乘以 3，告诉我最终数字。",
        "tools": [fibonacci, multiply],
        "check": lambda r: "165" in (r or ""),  # fib(10)=55, 55*3=165
        "expected": "包含 165",
    },
    {
        "name": "纯对话（无工具）",
        "prompt": "用一句话解释什么是 ReAct Agent。",
        "tools": [],
        "check": lambda r: len(r or "") > 10,
        "expected": "非空回答",
    },
]


def run_provider_test(provider_id: str, test_case: dict) -> dict:
    """对单个提供商运行一个测试用例，返回结果字典。"""
    cfg = get_provider_config(provider_id)
    if not cfg:
        return {"skipped": True, "reason": "未配置 API Key"}

    try:
        agent, _ = make_agent(
            provider_cfg=cfg,
            tools=test_case["tools"],
            system_prompt="你是一个精确的助手，使用工具完成计算任务，给出简洁准确的答案。",
            max_iterations=6,
        )

        t0 = time.perf_counter()
        answer = agent.run(test_case["prompt"])
        elapsed = time.perf_counter() - t0

        passed = test_case["check"](answer)
        return {
            "answer": answer,
            "elapsed": elapsed,
            "passed": passed,
            "skipped": False,
        }
    except Exception as e:
        return {"error": str(e), "skipped": False, "passed": False}


def demo_multi_provider_comparison():
    """横向对比所有提供商在相同问题上的表现。"""
    section("多提供商对比  工具调用准确性 + 响应质量")

    available = list_available_providers()
    if not available:
        err("未找到任何有效的 API Key，请检查 demos/.env")
        return

    names_str = ', '.join(f"{p['emoji']} {p['name']}" for p in available)
    print(f"\n  已配置提供商：{names_str}")

    for test in TEST_CASES:
        print(f"\n  {C.BOLD}📋 测试：{test['name']}{C.RESET}")
        print(f"  问题：{C.YELLOW}{test['prompt']}{C.RESET}")
        print(f"  预期：{test['expected']}")
        print()

        for p in available:
            provider_id = p["id"]
            print(f"  {p['emoji']} {p['name']} ({p['model']})", end=" ... ", flush=True)

            res = run_provider_test(provider_id, test)

            if res.get("skipped"):
                print(f"{C.GRAY}跳过（{res.get('reason', '?')}）{C.RESET}")
                continue
            if "error" in res:
                print(f"{C.RED}❌ 错误：{res['error'][:60]}{C.RESET}")
                continue

            status = f"{C.GREEN}✓{C.RESET}" if res["passed"] else f"{C.YELLOW}△{C.RESET}"
            answer_short = (res["answer"] or "")[:60].replace("\n", " ")
            print(f"{status} {res['elapsed']:.2f}s │ {answer_short}")

        print()


def demo_streaming_comparison():
    """比较各提供商流式输出的首 token 延迟。"""
    section("流式输出对比  首 token 延迟")

    available = list_available_providers()
    if not available:
        warn("无可用提供商")
        return

    prompt = "用 3 句话介绍一下你自己，包括你的能力和局限性。"
    print(f"  问题：{prompt}\n")

    latency_data = []

    for p in available:
        print(f"  {p['emoji']} {p['name']}  ", end="", flush=True)
        cfg = get_provider_config(p["id"])

        try:
            agent, _ = make_agent(provider_cfg=cfg)
            first_token_t = None
            full_text = ""
            t0 = time.perf_counter()

            for token in agent.run_stream(prompt):
                if first_token_t is None:
                    first_token_t = time.perf_counter() - t0
                full_text += token
                print("·", end="", flush=True)

            total_t = time.perf_counter() - t0
            chars = len(full_text)
            print(f"  首字：{first_token_t:.2f}s │ 总计：{total_t:.2f}s │ {chars} 字")
            latency_data.append((p["name"], first_token_t or 0, total_t, chars))

        except Exception as e:
            print(f"\n  ❌ {e}")

    if latency_data:
        fastest = min(latency_data, key=lambda x: x[1])
        print(f"\n  🏆 首字最快：{fastest[0]} ({fastest[1]:.2f}s)")


def demo_tool_call_accuracy():
    """深度测试：各提供商工具调用的准确性。"""
    section("工具调用准确性深度测试")

    available = list_available_providers()

    test_prompt = (
        "请完成以下计算：\n"
        "1. 计算斐波那契数列第 8 项\n"
        "2. 将上一步结果乘以 4\n"
        "3. 再加上 multiply(7, 3) 的结果\n"
        "给出每一步的中间结果和最终答案。"
    )
    # 正确答案：fib(8)=21, 21*4=84, 7*3=21, 84+21=105
    expected_answer = "105"

    print(f"  问题：多步骤计算（正确答案含 {expected_answer}）\n")

    scores = {}
    for p in available:
        cfg = get_provider_config(p["id"])
        print(f"  {p['emoji']} {p['name']}  ", end="", flush=True)

        try:
            agent, _ = make_agent(
                provider_cfg=cfg,
                tools=[add, multiply, fibonacci],
                max_iterations=8,
            )
            t0 = time.perf_counter()
            answer = agent.run(test_prompt)
            elapsed = time.perf_counter() - t0

            correct = expected_answer in answer
            scores[p["name"]] = correct
            status = f"{C.GREEN}✓ 正确{C.RESET}" if correct else f"{C.YELLOW}△ 答案可能有误{C.RESET}"
            answer_short = answer[:80].replace("\n", " ")
            print(f"{status} │ {elapsed:.2f}s\n    回答：{answer_short}")
        except Exception as e:
            scores[p["name"]] = False
            print(f"\n  ❌ {e}")

    if scores:
        correct_count = sum(scores.values())
        print(f"\n  准确率：{correct_count}/{len(scores)} 个提供商给出正确答案")


if __name__ == "__main__":
    header("演示 06：多模型提供商横向对比")

    available = list_available_providers()
    if not available:
        err("未找到任何有效的 API Key！")
        print("\n请编辑 demos/.env 填入至少一个 API Key")
        sys.exit(1)

    print(f"\n  已检测到 {len(available)} 个提供商：")
    for p in available:
        print(f"    {p['emoji']} {p['name']} — {p['model']}")

    try:
        demo_multi_provider_comparison()
        demo_streaming_comparison()
        demo_tool_call_accuracy()
        print(f"\n{'='*62}")
        ok("演示 06 全部完成！")
    except Exception as e:
        err(str(e))
        sys.exit(1)
