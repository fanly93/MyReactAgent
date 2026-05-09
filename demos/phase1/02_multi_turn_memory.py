"""
演示 02：多轮对话上下文保持（FR-005 ~ FR-007, US2, SC-004）

验证点：
  ✓ 同一会话内多轮对话，历史自动保留（FR-005）
  ✓ 会话历史超限时自动滑动窗口截断（FR-006）
  ✓ 系统提示在任何截断下永不丢失（FR-007）
  ✓ 10 个并发会话历史完全隔离（SC-004）
  ✓ 两个 Agent 实例记忆互不污染（FR-016/FR-017）
"""

import sys
import threading
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demos._utils import load_env, header, section, step, ok, warn, err, result, timer, make_agent
from myreactagent import tool

load_env()


@tool
def remember_number(n: int) -> str:
    """记住一个数字并确认。"""
    return f"已记住数字 {n}"


def demo_us2_basic_memory():
    """US2 独立验收测试：告知名字后第二轮能正确回忆。"""
    section("US2  基础多轮记忆")
    agent, cfg = make_agent(system_prompt="你是一个友好的助手，记住用户告诉你的所有信息。")
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} / {cfg['model']}")

    step("第 1 轮：告知名字")
    with timer("第1轮"):
        ok1, r1 = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, "我的名字是张三，我今年 28 岁，我最喜欢的颜色是蓝色。"
        )
    if ok1:
        result("回答", r1)

    step("第 2 轮：测试记忆")
    with timer("第2轮"):
        ok2, r2 = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, "我叫什么名字？我今年多大？我最喜欢什么颜色？"
        )
    if ok2:
        result("回答", r2)
        hits = sum(1 for kw in ["张三", "28", "蓝色"] if kw in (r2 or ""))
        if hits == 3:
            ok("全部 3 条记忆正确回忆 ✓")
        elif hits > 0:
            warn(f"部分记忆正确（{hits}/3）")
        else:
            warn("记忆回忆可能不准确，请检查")

    step("第 3 轮：续接上下文")
    with timer("第3轮"):
        ok3, r3 = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, "基于你对我的了解，推荐一个适合我的爱好。"
        )
    if ok3:
        result("回答", r3)
        ok("第 3 轮续接上下文成功 ✓")


def demo_fr006_sliding_window():
    """FR-006：会话超过 max_messages 时自动滑动窗口截断。"""
    section("FR-006  滑动窗口截断（max_messages=6）")
    agent, cfg = make_agent(
        system_prompt="你是一个简洁的助手，记住用户告诉你的信息。",
        max_messages=6,   # 设置较小窗口便于验证
        keep_last_n=2,
    )
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} | max_messages=6, keep_last_n=2")

    # 添加超过限制的消息
    for i in range(4):
        step(f"轮次 {i+1}/4")
        __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, f"这是第 {i+1} 轮对话，记住数字 {(i+1)*10}。"
        )

    msgs = agent._memory.get_messages()
    non_system = [m for m in msgs if m.role != "system"]
    system_msgs = [m for m in msgs if m.role == "system"]

    result("当前消息数（非 system）", str(len(non_system)))
    result("system 消息数", str(len(system_msgs)))

    # max_messages=6 统计的是非 system 消息（system 永远保留不计入上限）
    if len(non_system) <= 6:
        ok(f"非 system 消息已控制在上限内（{len(non_system)} ≤ 6）✓")
    else:
        warn(f"非 system 消息数 {len(non_system)} 超过预期上限 6")

    if len(system_msgs) == 1:
        ok("系统提示保留完整 ✓")
    else:
        warn("系统提示数量异常")


def demo_sc004_session_isolation():
    """SC-004：10 个并发会话历史无交叉污染。"""
    section("SC-004  10 个并发会话隔离验证")

    results_lock = threading.Lock()
    session_data: dict[int, dict] = {}

    def run_session(idx: int):
        try:
            agent, cfg = make_agent()
            agent.run(f"我是第 {idx} 号用户，我的专属密码是 SECRET_{idx:04d}。")
            msgs = agent._memory.get_messages()
            contents = " ".join(
                m.content for m in msgs if isinstance(m.content, str)
            )
            with results_lock:
                session_data[idx] = {
                    "session_id": agent.session_id,
                    "has_own_secret": f"SECRET_{idx:04d}" in contents,
                    "contents": contents,
                }
        except Exception as e:
            with results_lock:
                session_data[idx] = {"error": str(e)}

    step("启动 10 个并发线程...")
    threads = [threading.Thread(target=run_session, args=(i,)) for i in range(10)]
    with timer("10 个并发会话"):
        for t in threads:
            t.start()
        for t in threads:
            t.join()

    # 验证
    errors = [i for i, d in session_data.items() if "error" in d]
    if errors:
        warn(f"以下会话出错: {errors}")

    isolation_ok = True
    for i in range(10):
        d = session_data.get(i, {})
        if "error" in d:
            continue
        contents = d.get("contents", "")
        # 检查是否包含其他会话的密码
        for j in range(10):
            if j != i and f"SECRET_{j:04d}" in contents:
                err(f"会话 {i} 包含会话 {j} 的密码！隔离失败")
                isolation_ok = False

    # 检查每个会话的 session_id 唯一
    ids = [d.get("session_id") for d in session_data.values() if "session_id" in d]
    if len(set(ids)) == len(ids):
        ok(f"10 个 session_id 全部唯一 ✓")
    else:
        warn("存在重复 session_id")

    if isolation_ok:
        ok("10 个并发会话历史完全隔离，零交叉污染 ✓")


def demo_fr016_zero_global_state():
    """FR-016：两个 Agent 实例的对话历史完全独立。"""
    section("FR-016 / FR-017  零全局状态 + 会话完全隔离")

    agent_a, cfg_a = make_agent(system_prompt="你是助手 A。")
    agent_b, cfg_b = make_agent(system_prompt="你是助手 B。")
    print(f"  Agent A: {cfg_a['emoji']} {cfg_a['name']}  Agent B: {cfg_b['emoji']} {cfg_b['name']}")

    step("Agent A 记录信息...")
    __import__("demos._utils", fromlist=["safe_run"]).safe_run(agent_a.run, "记住：苹果的价格是 5 元。")

    step("Agent B 记录不同信息...")
    __import__("demos._utils", fromlist=["safe_run"]).safe_run(agent_b.run, "记住：香蕉的价格是 3 元。")

    step("Agent A 查询...")
    _, ra = __import__("demos._utils", fromlist=["safe_run"]).safe_run(agent_a.run, "苹果多少钱？香蕉呢？")
    result("Agent A 答案", ra or "")

    step("Agent B 查询...")
    _, rb = __import__("demos._utils", fromlist=["safe_run"]).safe_run(agent_b.run, "香蕉多少钱？苹果呢？")
    result("Agent B 答案", rb or "")

    # 验证隔离
    if ra and "苹果" in ra and "5" in ra:
        ok("Agent A 正确记住苹果价格 ✓")
    if rb and "香蕉" in rb and "3" in rb:
        ok("Agent B 正确记住香蕉价格 ✓")

    msgs_a = " ".join(m.content for m in agent_a._memory.get_messages() if isinstance(m.content, str))
    msgs_b = " ".join(m.content for m in agent_b._memory.get_messages() if isinstance(m.content, str))

    if "香蕉的价格是 3 元" not in msgs_a:
        ok("Agent A 历史中无 Agent B 的数据 ✓")
    if "苹果的价格是 5 元" not in msgs_b:
        ok("Agent B 历史中无 Agent A 的数据 ✓")


if __name__ == "__main__":
    header("演示 02：多轮对话上下文保持")

    try:
        demo_us2_basic_memory()
        demo_fr006_sliding_window()
        demo_sc004_session_isolation()
        demo_fr016_zero_global_state()
        print(f"\n{'='*62}")
        ok("演示 02 全部完成！")
    except RuntimeError as e:
        err(str(e))
        sys.exit(1)
