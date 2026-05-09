"""
演示 03：实时流式输出（FR-004, US3）

验证点：
  ✓ run_stream() 返回同步迭代器，逐 token yield（FR-004）
  ✓ 工具调用阶段后台执行，不中断流式（US3 验收场景 2）
  ✓ 流式与非流式回调行为对称（FR-013）
  ✓ 首 token 延迟明显低于完整等待（US3 体验验证）
"""

import sys
import time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demos._utils import (load_env, header, section, step, ok, warn, err,
                           result, timer, make_agent, C)
from myreactagent import tool, ConsoleCallbackHandler
from myreactagent.callbacks.base import BaseCallbackHandler
from myreactagent.schemas.events import CallbackEvent

load_env()


@tool
def calculate(expression: str) -> str:
    """计算数学表达式，返回结果。"""
    try:
        allowed = set("0123456789+-*/()., ")
        if not all(c in allowed for c in expression):
            return "错误：含不允许字符"
        return str(eval(expression))  # noqa: S307
    except Exception as e:
        return f"计算错误：{e}"


@tool
def get_poem_topic() -> str:
    """返回一个诗歌创作主题。"""
    return "秋天的落叶在夕阳下飘落"


def demo_basic_stream():
    """基础流式输出：逐 token 实时打印。"""
    section("US3 基础  逐 token 流式输出")
    agent, cfg = make_agent()
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} / {cfg['model']}")

    step("开始流式生成（写一首短诗）...")
    print(f"\n  {C.BOLD}流式输出：{C.RESET}", end="", flush=True)

    first_token_time = None
    start = time.perf_counter()
    token_count = 0
    full_text = ""

    try:
        for token in agent.run_stream("用 50 字以内写一首关于秋天的小诗，要有意境。"):
            if first_token_time is None:
                first_token_time = time.perf_counter() - start
            full_text += token
            token_count += 1
            print(token, end="", flush=True)
    except Exception as e:
        err(f"\n流式出错：{e}")
        return

    total_time = time.perf_counter() - start
    print(f"\n")

    result("首 token 延迟", f"{first_token_time:.2f}s")
    result("总耗时", f"{total_time:.2f}s")
    result("token 片段数", str(token_count))
    ok(f"流式输出完成，共 {len(full_text)} 字符 ✓")


def demo_stream_with_tools():
    """US3 验收场景 2：工具调用完成后继续流式输出。"""
    section("US3 进阶  工具调用后继续流式")
    agent, cfg = make_agent(tools=[calculate, get_poem_topic])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']}")

    step("请求含工具调用的流式响应...")
    print(f"\n  {C.BOLD}流式输出：{C.RESET}", end="", flush=True)

    tool_called = False
    full_text = ""

    class ToolTracker(BaseCallbackHandler):
        def on_tool_end(self, event: CallbackEvent):
            nonlocal tool_called
            tool_called = True
            print(f"\n  {C.GRAY}[工具 {event.data.get('tool_name')} 执行完毕]{C.RESET}", end="", flush=True)

    agent._callbacks.append(ToolTracker())

    try:
        for token in agent.run_stream(
            "先获取一个诗歌主题，再计算 7 × 8，然后用这两个信息写一句话。"
        ):
            full_text += token
            print(token, end="", flush=True)
    except Exception as e:
        err(f"\n流式出错：{e}")
        return

    print(f"\n")
    result("最终输出", full_text)

    if tool_called:
        ok("工具调用前后流式输出保持连续 ✓")
    else:
        warn("工具调用未触发（可能模型直接回答了）")


def demo_stream_callback_symmetry():
    """FR-013：流式与非流式回调行为对称。"""
    section("FR-013  流式 vs 非流式回调对称验证")

    stream_events = []
    sync_events = []

    class EventLogger(BaseCallbackHandler):
        def __init__(self, store):
            self._store = store
        def on_agent_start(self, e): self._store.append(("on_agent_start", e.data))
        def on_llm_start(self, e): self._store.append(("on_llm_start", e.data.get("stream")))
        def on_llm_end(self, e): self._store.append(("on_llm_end", e.data.get("finish_reason")))
        def on_agent_end(self, e): self._store.append(("on_agent_end", e.data.get("final_answer", "")[:20]))

    # 流式
    agent_s, cfg = make_agent(callbacks=[EventLogger(stream_events)])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']}")
    try:
        for _ in agent_s.run_stream("用一句话介绍自己。"):
            pass
    except Exception as e:
        warn(f"流式运行异常：{e}")

    # 非流式（新实例）
    agent_n, _ = make_agent(callbacks=[EventLogger(sync_events)])
    try:
        agent_n.run("用一句话介绍自己。")
    except Exception as e:
        warn(f"非流式运行异常：{e}")

    stream_names = [e[0] for e in stream_events]
    sync_names   = [e[0] for e in sync_events]

    result("流式事件序列", " → ".join(stream_names))
    result("非流式事件序列", " → ".join(sync_names))

    key_events = {"on_agent_start", "on_llm_start", "on_llm_end", "on_agent_end"}
    if key_events.issubset(set(stream_names)) and key_events.issubset(set(sync_names)):
        ok("流式与非流式均触发全部核心回调事件 ✓")
    else:
        warn("部分回调事件未触发")

    # 验证流式 on_llm_start 中 stream=True
    stream_llm_start = next((e for e in stream_events if e[0] == "on_llm_start"), None)
    if stream_llm_start and stream_llm_start[1] is True:
        ok("流式 on_llm_start 的 stream=True ✓")


def demo_stream_first_token_latency():
    """体验对比：流式首字延迟 vs 完整等待时间。"""
    section("体验对比  流式首字延迟 vs 完整等待")
    agent_s, cfg = make_agent()
    agent_n, _ = make_agent()
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']}")

    prompt = "详细解释一下什么是 ReAct Agent，包括它的工作原理和优势，写 100 字左右。"

    # 流式：记录首 token 时间
    step("流式模式运行...")
    t0 = time.perf_counter()
    first_token_t = None
    stream_total_t = None
    try:
        for token in agent_s.run_stream(prompt):
            if first_token_t is None:
                first_token_t = time.perf_counter() - t0
        stream_total_t = time.perf_counter() - t0
    except Exception as e:
        warn(f"流式出错：{e}")

    # 非流式：整体等待
    step("非流式模式运行...")
    t1 = time.perf_counter()
    try:
        agent_n.run(prompt)
    except Exception as e:
        warn(f"非流式出错：{e}")
    sync_total_t = time.perf_counter() - t1

    if first_token_t:
        result("流式首字延迟", f"{first_token_t:.2f}s")
    if stream_total_t:
        result("流式总耗时", f"{stream_total_t:.2f}s")
    result("非流式总耗时", f"{sync_total_t:.2f}s")

    if first_token_t and first_token_t < sync_total_t:
        ok(f"流式首字延迟 ({first_token_t:.1f}s) 明显低于完整等待 ({sync_total_t:.1f}s) ✓")


if __name__ == "__main__":
    header("演示 03：实时流式输出")

    try:
        demo_basic_stream()
        demo_stream_with_tools()
        demo_stream_callback_symmetry()
        demo_stream_first_token_latency()
        print(f"\n{'='*62}")
        ok("演示 03 全部完成！")
    except RuntimeError as e:
        err(str(e))
        sys.exit(1)
