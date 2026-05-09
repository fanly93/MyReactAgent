"""LLMClient 非流式单元测试（mock openai.OpenAI）。"""

import pytest
from unittest.mock import MagicMock, patch

from myreactagent.llm.client import LLMClient
from myreactagent.schemas.messages import Message


def make_completion(finish_reason: str = "stop", content: str = "测试回答", tool_calls=None):
    """构建 mock ChatCompletion 对象。"""
    choice = MagicMock()
    choice.finish_reason = finish_reason
    choice.message.content = content
    choice.message.tool_calls = tool_calls
    completion = MagicMock()
    completion.choices = [choice]
    return completion


class TestLLMClientInit:
    def test_default_model_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        with patch("openai.OpenAI"):
            client = LLMClient()
        assert client.model == "gpt-4o"

    def test_explicit_model_overrides_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
        with patch("openai.OpenAI"):
            client = LLMClient(model="gpt-4o-mini")
        assert client.model == "gpt-4o-mini"

    def test_default_model_fallback(self, monkeypatch):
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        with patch("openai.OpenAI"):
            client = LLMClient()
        assert client.model == "gpt-4o-mini"

    def test_max_retries_is_3(self):
        with patch("openai.OpenAI") as mock_openai:
            LLMClient()
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs.get("max_retries") == 3

    def test_base_url_from_env(self, monkeypatch):
        monkeypatch.setenv("OPENAI_BASE_URL", "https://custom.api.com")
        with patch("openai.OpenAI") as mock_openai:
            LLMClient()
        call_kwargs = mock_openai.call_args.kwargs
        assert call_kwargs.get("base_url") == "https://custom.api.com"

    def test_no_base_url_when_not_set(self, monkeypatch):
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        with patch("openai.OpenAI") as mock_openai:
            LLMClient()
        call_kwargs = mock_openai.call_args.kwargs
        assert "base_url" not in call_kwargs


class TestLLMClientChat:
    def setup_method(self):
        with patch("openai.OpenAI"):
            self.client = LLMClient(model="gpt-4o-mini")

    def test_chat_finish_reason_stop(self):
        completion = make_completion(finish_reason="stop", content="最终答案")
        self.client._client.chat.completions.create.return_value = completion

        messages = [Message(role="user", content="你好")]
        result = self.client.chat(messages)

        assert result.choices[0].finish_reason == "stop"
        assert result.choices[0].message.content == "最终答案"

    def test_chat_finish_reason_tool_calls(self):
        tool_call = MagicMock()
        tool_call.id = "call_123"
        tool_call.function.name = "add"
        tool_call.function.arguments = '{"a": 1, "b": 2}'
        completion = make_completion(finish_reason="tool_calls", tool_calls=[tool_call])
        self.client._client.chat.completions.create.return_value = completion

        messages = [Message(role="user", content="计算 1+2")]
        result = self.client.chat(messages, tools=[{"type": "function", "function": {"name": "add"}}])

        assert result.choices[0].finish_reason == "tool_calls"
        assert result.choices[0].message.tool_calls[0].id == "call_123"

    def test_chat_passes_messages_correctly(self):
        completion = make_completion()
        self.client._client.chat.completions.create.return_value = completion

        messages = [
            Message(role="system", content="系统提示"),
            Message(role="user", content="用户输入"),
        ]
        self.client.chat(messages)

        call_kwargs = self.client._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["model"] == "gpt-4o-mini"
        assert len(call_kwargs["messages"]) == 2
        assert call_kwargs["messages"][0]["role"] == "system"

    def test_chat_no_tools_when_none(self):
        completion = make_completion()
        self.client._client.chat.completions.create.return_value = completion

        self.client.chat([Message(role="user", content="test")])

        call_kwargs = self.client._client.chat.completions.create.call_args.kwargs
        assert "tools" not in call_kwargs

    def test_chat_passes_tools_when_provided(self):
        completion = make_completion()
        self.client._client.chat.completions.create.return_value = completion

        tools = [{"type": "function", "function": {"name": "calc"}}]
        self.client.chat([Message(role="user", content="test")], tools=tools)

        call_kwargs = self.client._client.chat.completions.create.call_args.kwargs
        assert call_kwargs["tools"] == tools
