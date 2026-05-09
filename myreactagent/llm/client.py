from __future__ import annotations

import os
from typing import Iterator

import openai

from myreactagent.schemas.messages import Message


class LLMClient:
    """OpenAI SDK 薄封装，提供非流式和流式两种调用接口。"""

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.model = model or os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
        resolved_base_url = base_url or os.environ.get("OPENAI_BASE_URL")
        resolved_api_key = api_key or os.environ.get("OPENAI_API_KEY")

        kwargs: dict = {"max_retries": 3}
        if resolved_base_url:
            kwargs["base_url"] = resolved_base_url
        if resolved_api_key:
            kwargs["api_key"] = resolved_api_key

        self._client = openai.OpenAI(**kwargs)

    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> openai.types.chat.ChatCompletion:
        """非流式调用，返回完整的 ChatCompletion 对象。ReactAgent.run() 使用。"""
        openai_messages = [m.to_openai_dict() for m in messages]
        kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
        }
        if tools:
            kwargs["tools"] = tools

        return self._client.chat.completions.create(**kwargs)

    def chat_stream(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
    ) -> Iterator[openai.types.chat.ChatCompletionChunk]:
        """流式调用，原样透传 SDK 的同步 chunks 迭代器。ReactAgent.run_stream() 使用。"""
        openai_messages = [m.to_openai_dict() for m in messages]
        kwargs: dict = {
            "model": self.model,
            "messages": openai_messages,
            "stream": True,
        }
        if tools:
            kwargs["tools"] = tools

        return self._client.chat.completions.create(**kwargs)
