"""ReactAgent 单元测试（mock LLMClient）。"""

import pytest
from unittest.mock import MagicMock, patch

from myreactagent.agent.react import ReactAgent
from myreactagent.tools.decorator import tool
from myreactagent.callbacks.base import BaseCallbackHandler
from myreactagent.schemas.events import CallbackEvent


# ── 测试用工具 ──────────────────────────────────────────────────────────────────

@tool
def add(a: int, b: int) -> int:
    """将两个整数相加。"""
    return a + b


@tool
def fail_always(msg: str) -> str:
    """总是失败的工具。"""
    raise RuntimeError("工具执行失败")


# ── Mock 构建辅助 ───────────────────────────────────────────────────────────────

def _make_stop_response(content: str = "最终答案"):
    choice = MagicMock()
    choice.finish_reason = "stop"
    choice.message.content = content
    choice.message.tool_calls = None
    resp = MagicMock()
    resp.choices = [choice]
    return resp


def _make_tool_call_response(tool_name: str, args_json: str, call_id: str = "call_001"):
    tc = MagicMock()
    tc.id = call_id
    tc.function.name = tool_name
    tc.function.arguments = args_json
    choice = MagicMock()
    choice.finish_reason = "tool_calls"
    choice.message.content = ""
    choice.message.tool_calls = [tc]
    resp = MagicMock()
    resp.choices = [choice]
    return resp


# ── 测试类 ─────────────────────────────────────────────────────────────────────

class TestReactAgentRun:
    def _make_agent(self, tools=None, callbacks=None, max_iterations=5):
        with patch("myreactagent.llm.client.openai.OpenAI"):
            return ReactAgent(
                tools=tools or [],
                max_iterations=max_iterations,
                callbacks=callbacks or [],
            )

    def test_single_stop_loop(self):
        agent = self._make_agent()
        agent._llm._client.chat.completions.create.return_value = _make_stop_response("你好！")
        result = agent.run("测试")
        assert result == "你好！"

    def test_one_tool_call_then_stop(self):
        agent = self._make_agent(tools=[add])
        agent._llm._client.chat.completions.create.side_effect = [
            _make_tool_call_response("add", '{"a": 3, "b": 4}'),
            _make_stop_response("结果是 7"),
        ]
        result = agent.run("3 加 4 等于多少？")
        assert result == "结果是 7"

    def test_multiple_tool_calls_same_round(self):
        tc1 = MagicMock()
        tc1.id = "call_001"
        tc1.function.name = "add"
        tc1.function.arguments = '{"a": 1, "b": 2}'
        tc2 = MagicMock()
        tc2.id = "call_002"
        tc2.function.name = "add"
        tc2.function.arguments = '{"a": 3, "b": 4}'
        choice = MagicMock()
        choice.finish_reason = "tool_calls"
        choice.message.content = ""
        choice.message.tool_calls = [tc1, tc2]
        resp = MagicMock()
        resp.choices = [choice]

        agent = self._make_agent(tools=[add])
        agent._llm._client.chat.completions.create.side_effect = [resp, _make_stop_response("完成")]
        result = agent.run("计算两次")
        assert result == "完成"

    def test_tool_execution_failure_loop_continues(self):
        agent = self._make_agent(tools=[fail_always])
        agent._llm._client.chat.completions.create.side_effect = [
            _make_tool_call_response("fail_always", '{"msg": "test"}'),
            _make_stop_response("尽管工具失败，仍继续"),
        ]
        result = agent.run("调用失败工具")
        assert result == "尽管工具失败，仍继续"

    def test_max_iterations_safety_fallback(self):
        """达到 max_iterations 时触发安全兜底，再调一次 LLM 返回答案。"""
        agent = self._make_agent(tools=[add], max_iterations=2)
        # 始终返回 tool_calls（会循环直到耗尽），最后安全兜底返回 stop
        agent._llm._client.chat.completions.create.side_effect = [
            _make_tool_call_response("add", '{"a": 1, "b": 1}'),
            _make_tool_call_response("add", '{"a": 2, "b": 2}'),
            _make_stop_response("安全兜底答案"),  # 兜底 LLM 调用
        ]
        result = agent.run("无限循环测试")
        assert result == "安全兜底答案"

    def test_empty_tools_pure_chat_mode(self):
        agent = self._make_agent(tools=[])
        agent._llm._client.chat.completions.create.return_value = _make_stop_response("纯对话回答")
        result = agent.run("你好")
        assert result == "纯对话回答"

    def test_system_prompt_is_first_message(self):
        agent = self._make_agent()
        agent.system_prompt = "你是一个测试助手"
        # 替换 _memory 中的系统消息
        from myreactagent.schemas.messages import Message
        agent._memory.clear()
        agent._memory.add(Message(role="system", content="你是一个测试助手"))

        agent._llm._client.chat.completions.create.return_value = _make_stop_response("回答")
        agent.run("问题")

        call_kwargs = agent._llm._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["messages"][0]["role"] == "system"


class TestReactAgentSessionIsolation:
    """验证两个独立 Agent 实例的历史完全隔离（宪法 XII，T021）。"""

    def test_two_agents_have_independent_history(self):
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent1 = ReactAgent()
            agent2 = ReactAgent()

        agent1._llm._client.chat.completions.create.return_value = _make_stop_response("Agent1 回答")
        agent2._llm._client.chat.completions.create.return_value = _make_stop_response("Agent2 回答")

        agent1.run("Agent1 的问题")
        agent2.run("Agent2 的问题")

        msgs1 = agent1._memory.get_messages()
        msgs2 = agent2._memory.get_messages()

        # 历史互不干扰
        contents1 = [m.content for m in msgs1]
        contents2 = [m.content for m in msgs2]
        assert "Agent1 的问题" in contents1
        assert "Agent2 的问题" not in contents1
        assert "Agent2 的问题" in contents2
        assert "Agent1 的问题" not in contents2

    def test_session_ids_are_unique(self):
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent1 = ReactAgent()
            agent2 = ReactAgent()
        assert agent1.session_id != agent2.session_id


class TestReactAgentCallbacks:
    """验证回调事件正确触发。"""

    def _collect_events(self):
        events = []

        class Collector(BaseCallbackHandler):
            def on_agent_start(self, event: CallbackEvent):
                events.append(("on_agent_start", event.data))

            def on_llm_start(self, event: CallbackEvent):
                events.append(("on_llm_start", event.data))

            def on_llm_end(self, event: CallbackEvent):
                events.append(("on_llm_end", event.data))

            def on_tool_start(self, event: CallbackEvent):
                events.append(("on_tool_start", event.data))

            def on_tool_end(self, event: CallbackEvent):
                events.append(("on_tool_end", event.data))

            def on_agent_end(self, event: CallbackEvent):
                events.append(("on_agent_end", event.data))

            def on_error(self, event: CallbackEvent):
                events.append(("on_error", event.data))

        return events, Collector()

    def test_stop_loop_events_order(self):
        events, collector = self._collect_events()
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(callbacks=[collector])
        agent._llm._client.chat.completions.create.return_value = _make_stop_response("回答")
        agent.run("问题")

        names = [e[0] for e in events]
        assert names == ["on_agent_start", "on_llm_start", "on_llm_end", "on_agent_end"]

    def test_tool_call_events_order(self):
        events, collector = self._collect_events()
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(tools=[add], callbacks=[collector])
        agent._llm._client.chat.completions.create.side_effect = [
            _make_tool_call_response("add", '{"a": 1, "b": 2}'),
            _make_stop_response("结果"),
        ]
        agent.run("计算")

        names = [e[0] for e in events]
        assert "on_tool_start" in names
        assert "on_tool_end" in names
        # 工具调用发生在两次 LLM 调用之间
        tool_start_idx = names.index("on_tool_start")
        first_llm_end_idx = names.index("on_llm_end")
        assert tool_start_idx > first_llm_end_idx

    def test_callback_exception_does_not_break_agent(self):
        class BrokenCallback(BaseCallbackHandler):
            def on_agent_start(self, event):
                raise RuntimeError("回调崩溃")

        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(callbacks=[BrokenCallback()])
        agent._llm._client.chat.completions.create.return_value = _make_stop_response("正常回答")
        result = agent.run("测试")
        assert result == "正常回答"

    def test_on_tool_end_success_payload_format(self):
        """验证 on_tool_end 成功时的载荷符合 contracts §4 六字段格式。"""
        events, collector = self._collect_events()
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(tools=[add], callbacks=[collector])
        agent._llm._client.chat.completions.create.side_effect = [
            _make_tool_call_response("add", '{"a": 1, "b": 2}'),
            _make_stop_response("结果是 3"),
        ]
        agent.run("计算")

        tool_end_events = [e for e in events if e[0] == "on_tool_end"]
        assert len(tool_end_events) == 1
        data = tool_end_events[0][1]
        assert data["success"] is True
        assert data["result"] is not None  # 成功时有内容
        assert data["error_type"] is None
        assert data["error_message"] is None

    def test_on_tool_end_failure_payload_format(self):
        """验证 on_tool_end 失败时的载荷符合 contracts §4 六字段格式。"""
        events, collector = self._collect_events()
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(tools=[fail_always], callbacks=[collector])
        agent._llm._client.chat.completions.create.side_effect = [
            _make_tool_call_response("fail_always", '{"msg": "test"}'),
            _make_stop_response("继续"),
        ]
        agent.run("触发失败工具")

        tool_end_events = [e for e in events if e[0] == "on_tool_end"]
        assert len(tool_end_events) == 1
        data = tool_end_events[0][1]
        assert data["success"] is False
        assert data["result"] is None  # 失败时 result 为 null
        assert data["error_type"] == "RuntimeError"
        assert data["error_message"] is not None

    def test_system_prompt_too_long_emits_warning(self):
        """验证超长系统提示触发 on_error warning（MC-002）。"""
        events, collector = self._collect_events()
        long_prompt = "x" * 9000  # 超过 _MAX_SYSTEM_PROMPT_CHARS=8000
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(system_prompt=long_prompt, callbacks=[collector])
        agent._llm._client.chat.completions.create.return_value = _make_stop_response("回答")
        agent.run("测试")

        error_events = [e for e in events if e[0] == "on_error"]
        assert any(
            e[1].get("warning") is True and e[1].get("error_type") == "SystemPromptTooLong"
            for e in error_events
        )

    def test_system_prompt_warning_emitted_only_once(self):
        """验证超长系统提示 warning 在多次 run() 中只发出一次。"""
        events, collector = self._collect_events()
        long_prompt = "x" * 9000
        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(system_prompt=long_prompt, callbacks=[collector])
        agent._llm._client.chat.completions.create.return_value = _make_stop_response("回答")
        agent.run("第一次")
        agent.run("第二次")

        warning_events = [
            e for e in events
            if e[0] == "on_error" and e[1].get("error_type") == "SystemPromptTooLong"
        ]
        assert len(warning_events) == 1
