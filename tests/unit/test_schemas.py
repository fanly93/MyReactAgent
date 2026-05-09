"""schemas 模块单元测试：覆盖 Message、ToolResult、CallbackEvent、NextStep。"""

import pytest
from pydantic import ValidationError

from myreactagent.schemas import (
    CallbackEvent,
    ImageContentPart,
    Message,
    NextStep,
    TextContentPart,
    ToolCall,
    ToolCallFunction,
    ToolResult,
)


class TestMessage:
    def test_to_openai_dict_system(self):
        msg = Message(role="system", content="你是一个助手。")
        d = msg.to_openai_dict()
        assert d == {"role": "system", "content": "你是一个助手。"}

    def test_to_openai_dict_user(self):
        msg = Message(role="user", content="你好")
        d = msg.to_openai_dict()
        assert d == {"role": "user", "content": "你好"}

    def test_to_openai_dict_assistant_plain(self):
        msg = Message(role="assistant", content="我来帮你。")
        d = msg.to_openai_dict()
        assert d == {"role": "assistant", "content": "我来帮你。"}

    def test_to_openai_dict_assistant_with_tool_calls(self):
        tc = ToolCall(
            id="call_123",
            function=ToolCallFunction(name="calc", arguments='{"a": 1}'),
        )
        msg = Message(role="assistant", content="", tool_calls=[tc])
        d = msg.to_openai_dict()
        assert d["role"] == "assistant"
        assert d["content"] == ""
        assert len(d["tool_calls"]) == 1
        assert d["tool_calls"][0]["id"] == "call_123"
        assert d["tool_calls"][0]["type"] == "function"
        assert d["tool_calls"][0]["function"]["name"] == "calc"
        assert d["tool_calls"][0]["function"]["arguments"] == '{"a": 1}'

    def test_to_openai_dict_tool_role(self):
        msg = Message(
            role="tool",
            content="42",
            tool_call_id="call_123",
            name="calc",
        )
        d = msg.to_openai_dict()
        assert d["role"] == "tool"
        assert d["content"] == "42"
        assert d["tool_call_id"] == "call_123"
        assert d["name"] == "calc"

    def test_to_openai_dict_excludes_none_fields(self):
        msg = Message(role="user", content="hello")
        d = msg.to_openai_dict()
        assert "tool_calls" not in d
        assert "tool_call_id" not in d
        assert "name" not in d

    def test_to_openai_dict_list_content_raises(self):
        # Phase 1 不支持 list[ContentPart]，必须抛出 NotImplementedError
        part = TextContentPart(text="hello")
        msg = Message(role="user", content=[part])
        with pytest.raises(NotImplementedError, match="Phase 1"):
            msg.to_openai_dict()

    def test_message_invalid_role(self):
        with pytest.raises(ValidationError):
            Message(role="invalid_role", content="test")

    def test_message_list_content_is_valid_model(self):
        # Pydantic 模型本身接受 list[ContentPart]，仅在 to_openai_dict 时拒绝
        part = ImageContentPart(image_url={"url": "http://example.com/img.png"})
        msg = Message(role="user", content=[part])
        assert isinstance(msg.content, list)


class TestToolResult:
    def test_to_message_success(self):
        result = ToolResult(tool_call_id="call_abc", success=True, content="计算结果：42")
        msg = result.to_message()
        assert msg.role == "tool"
        assert msg.tool_call_id == "call_abc"
        assert msg.content == "计算结果：42"

    def test_to_message_failure(self):
        result = ToolResult(
            tool_call_id="call_abc",
            success=False,
            error="除数不能为零",
        )
        msg = result.to_message()
        assert msg.role == "tool"
        assert msg.content == "除数不能为零"

    def test_to_message_failure_no_error(self):
        result = ToolResult(tool_call_id="call_abc", success=False)
        msg = result.to_message()
        assert msg.content == "error"

    def test_tool_result_default_content(self):
        result = ToolResult(tool_call_id="call_x", success=True)
        assert result.content == ""

    def test_tool_result_validation(self):
        with pytest.raises(ValidationError):
            ToolResult(success=True, content="test")  # 缺少 tool_call_id


class TestNextStep:
    def test_all_values_exist(self):
        assert NextStep.STOP.value == "stop"
        assert NextStep.CONTINUE.value == "continue"
        assert NextStep.HANDOFF.value == "handoff"
        assert NextStep.INTERRUPT.value == "interrupt"

    def test_enum_count(self):
        assert len(NextStep) == 4


class TestCallbackEvent:
    def test_required_fields(self):
        event = CallbackEvent(
            event="on_agent_start",
            data={"user_message": "hello"},
            timestamp="2026-05-08T10:00:00Z",
            session_id="sess-001",
            run_id="run-001",
        )
        assert event.event == "on_agent_start"
        assert event.span_id == ""  # Phase 1 默认空字符串

    def test_span_id_default_empty(self):
        event = CallbackEvent(
            event="on_tool_start",
            data={},
            timestamp="2026-05-08T10:00:00Z",
            session_id="s1",
            run_id="r1",
        )
        assert event.span_id == ""

    def test_custom_span_id(self):
        event = CallbackEvent(
            event="on_llm_end",
            data={},
            timestamp="2026-05-08T10:00:00Z",
            session_id="s1",
            run_id="r1",
            span_id="otel-span-xyz",
        )
        assert event.span_id == "otel-span-xyz"

    def test_missing_required_fields(self):
        with pytest.raises(ValidationError):
            CallbackEvent(event="on_agent_start", data={})  # 缺少 timestamp 等字段
