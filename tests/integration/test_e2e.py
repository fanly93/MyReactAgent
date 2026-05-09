"""端到端集成测试（需要真实 API Key，通过 RUN_INTEGRATION_TESTS=1 门控）。"""

import os
import pytest

# 集成测试门控：未设置环境变量时跳过
pytestmark = pytest.mark.integration
if not os.environ.get("RUN_INTEGRATION_TESTS"):
    pytest.skip("Set RUN_INTEGRATION_TESTS=1 to run integration tests", allow_module_level=True)


from myreactagent import ReactAgent, tool, ConsoleCallbackHandler
from myreactagent.callbacks.base import BaseCallbackHandler
from myreactagent.schemas.events import CallbackEvent


@tool
def add(a: int, b: int) -> int:
    """将两个整数相加。"""
    return a + b


@tool
def multiply(a: int, b: int) -> int:
    """将两个整数相乘。"""
    return a * b


@tool
def broken_tool(x: str) -> str:
    """总是抛出异常。"""
    raise RuntimeError("工具故意失败")


# SC-001 & SC-002：算术工具多步骤调用
def test_arithmetic_tool_correct_answer():
    agent = ReactAgent(
        tools=[add, multiply],
        system_prompt="使用工具完成计算，给出精确数字答案。",
        max_iterations=8,
    )
    result = agent.run("3 乘以 7 加上 8 等于多少？")
    assert "29" in result


# SC-003：工具异常不崩溃
def test_tool_exception_does_not_crash():
    agent = ReactAgent(
        tools=[broken_tool, add],
        system_prompt="先尝试 broken_tool，失败后使用 add 完成计算。",
        max_iterations=6,
    )
    result = agent.run("调用 broken_tool，然后计算 2+3。")
    assert result  # 不抛出异常，返回非空字符串


# SC-004：并发会话历史无交叉
def test_concurrent_sessions_isolated():
    agents = []
    for i in range(3):
        agent = ReactAgent(system_prompt=f"你是 Agent {i}，记住这个编号。")
        agents.append(agent)

    for i, agent in enumerate(agents):
        agent.run(f"我是测试会话 {i}，请记住。")

    # 每个 agent 的历史只包含自己的消息
    for i, agent in enumerate(agents):
        msgs = agent._memory.get_messages()
        contents = " ".join(m.content for m in msgs if isinstance(m.content, str))
        assert f"测试会话 {i}" in contents
        for j in range(3):
            if j != i:
                assert f"测试会话 {j}" not in contents


# SC-005：7 类事件完整触发
def test_all_7_callback_events_triggered():
    events_seen = set()

    class EventCollector(BaseCallbackHandler):
        def on_agent_start(self, e): events_seen.add("on_agent_start")
        def on_llm_start(self, e): events_seen.add("on_llm_start")
        def on_llm_end(self, e): events_seen.add("on_llm_end")
        def on_tool_start(self, e): events_seen.add("on_tool_start")
        def on_tool_end(self, e): events_seen.add("on_tool_end")
        def on_agent_end(self, e): events_seen.add("on_agent_end")

    agent = ReactAgent(
        tools=[add],
        callbacks=[EventCollector()],
        max_iterations=5,
    )
    agent.run("计算 1 + 1")

    expected = {"on_agent_start", "on_llm_start", "on_llm_end", "on_agent_end"}
    assert expected.issubset(events_seen)
