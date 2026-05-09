"""BaseCallbackHandler 和 ConsoleCallbackHandler 单元测试（T026）。"""

import pytest
from myreactagent.callbacks.base import BaseCallbackHandler
from myreactagent.callbacks.console import ConsoleCallbackHandler
from myreactagent.schemas.events import CallbackEvent


def _make_event(event_name: str, data: dict | None = None) -> CallbackEvent:
    return CallbackEvent(
        event=event_name,
        data=data or {},
        timestamp="2026-05-08T10:00:00.000Z",
        session_id="sess-test",
        run_id="run-test",
    )


class TestBaseCallbackHandler:
    def test_all_methods_are_no_ops(self):
        handler = BaseCallbackHandler()
        event = _make_event("on_agent_start")
        # 所有方法调用不报错
        handler.on_agent_start(event)
        handler.on_llm_start(event)
        handler.on_llm_end(event)
        handler.on_tool_start(event)
        handler.on_tool_end(event)
        handler.on_agent_end(event)
        handler.on_error(event)

    def test_subclass_can_override_selectively(self):
        called = []

        class Partial(BaseCallbackHandler):
            def on_agent_start(self, event):
                called.append("start")

        handler = Partial()
        handler.on_agent_start(_make_event("on_agent_start"))
        handler.on_llm_start(_make_event("on_llm_start"))  # 未覆盖，不报错
        assert called == ["start"]


class TestConsoleCallbackHandler:
    def test_on_agent_start_output(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_agent_start",
            {"user_message": "测试问题", "system_prompt": "系统提示"},
        )
        handler.on_agent_start(event)
        captured = capsys.readouterr()
        assert "Agent 启动" in captured.out
        assert "测试问题" in captured.out

    def test_on_llm_start_output(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event("on_llm_start", {"stream": False, "tools": [{"name": "calc"}]})
        handler.on_llm_start(event)
        captured = capsys.readouterr()
        assert "LLM" in captured.out
        assert "tools=1" in captured.out

    def test_on_llm_end_with_tool_calls(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_llm_end",
            {
                "content": "",
                "tool_calls": [{"name": "add", "id": "call_1", "arguments": "{}"}],
                "finish_reason": "tool_calls",
            },
        )
        handler.on_llm_end(event)
        captured = capsys.readouterr()
        assert "add" in captured.out
        assert "tool_calls" in captured.out

    def test_on_llm_end_without_tool_calls(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_llm_end",
            {"content": "最终答案内容", "tool_calls": None, "finish_reason": "stop"},
        )
        handler.on_llm_end(event)
        captured = capsys.readouterr()
        assert "stop" in captured.out
        assert "最终答案内容" in captured.out

    def test_on_tool_start_output(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_tool_start",
            {"tool_name": "search", "tool_call_id": "call_99", "arguments": {"query": "Python"}},
        )
        handler.on_tool_start(event)
        captured = capsys.readouterr()
        assert "search" in captured.out
        assert "call_99" in captured.out

    def test_on_tool_end_success(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_tool_end",
            {"tool_name": "calc", "tool_call_id": "call_1", "success": True, "result": "42"},
        )
        handler.on_tool_end(event)
        captured = capsys.readouterr()
        assert "42" in captured.out
        assert "✓" in captured.out

    def test_on_tool_end_failure(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_tool_end",
            {"tool_name": "calc", "tool_call_id": "call_1", "success": False, "result": "错误"},
        )
        handler.on_tool_end(event)
        captured = capsys.readouterr()
        assert "✗" in captured.out

    def test_on_agent_end_output(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_agent_end",
            {"final_answer": "最终答案", "iterations": 3},
        )
        handler.on_agent_end(event)
        captured = capsys.readouterr()
        assert "完成" in captured.out
        assert "3" in captured.out

    def test_on_error_output(self, capsys):
        handler = ConsoleCallbackHandler()
        event = _make_event(
            "on_error",
            {
                "error_type": "JSONDecodeError",
                "error_message": "无效 JSON",
                "context": "解析参数失败",
            },
        )
        handler.on_error(event)
        captured = capsys.readouterr()
        assert "JSONDecodeError" in captured.out
        assert "无效 JSON" in captured.out


class TestCallbackExceptionIsolation:
    """验证框架的回调异常隔离（T026 中 _emit try/except 保护）。"""

    def test_emit_protects_against_broken_callback(self):
        """通过 ReactAgent._emit 验证单个回调崩溃不影响后续回调。"""
        from unittest.mock import patch
        from myreactagent.agent.react import ReactAgent

        call_log = []

        class BrokenCallback(BaseCallbackHandler):
            def on_agent_start(self, event):
                raise RuntimeError("回调崩溃")

        class GoodCallback(BaseCallbackHandler):
            def on_agent_start(self, event):
                call_log.append("good_callback_called")

        with patch("myreactagent.llm.client.openai.OpenAI"):
            agent = ReactAgent(callbacks=[BrokenCallback(), GoodCallback()])

        agent._llm._client.chat.completions.create.return_value = MagicMock(
            choices=[MagicMock(finish_reason="stop", message=MagicMock(content="回答", tool_calls=None))]
        )
        agent.run("测试")
        assert "good_callback_called" in call_log


from unittest.mock import MagicMock
