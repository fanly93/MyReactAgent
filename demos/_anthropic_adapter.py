"""Anthropic Claude 原生 SDK 适配器，将 Claude API 包装为 ReactAgent 可用的接口。

Anthropic 使用自己的 REST 格式，不完全兼容 OpenAI protocol，
因此通过此适配器桥接，实现与 ReactAgent 相同的 run() / run_stream() 接口。
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Iterator

try:
    import anthropic as _anthropic_sdk
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _openai_tools_to_anthropic(tools: list[dict]) -> list[dict]:
    """将 OpenAI function calling 格式转换为 Anthropic tools 格式。"""
    result = []
    for t in tools:
        fn = t.get("function", {})
        result.append({
            "name": fn["name"],
            "description": fn.get("description", ""),
            "input_schema": fn.get("parameters", {"type": "object", "properties": {}}),
        })
    return result


def _openai_messages_to_anthropic(messages: list) -> tuple[str | None, list[dict]]:
    """将 OpenAI 消息格式转换为 Anthropic 格式，分离 system 消息。"""
    system = None
    anthropic_messages = []

    for msg in messages:
        role = msg.get("role")
        content = msg.get("content", "")

        if role == "system":
            system = content
            continue

        if role == "user":
            anthropic_messages.append({"role": "user", "content": content or ""})

        elif role == "assistant":
            tool_calls = msg.get("tool_calls")
            if tool_calls:
                # assistant 消息含工具调用 → Anthropic tool_use 格式
                blocks = []
                if content:
                    blocks.append({"type": "text", "text": content})
                for tc in tool_calls:
                    fn = tc["function"]
                    blocks.append({
                        "type": "tool_use",
                        "id": tc["id"],
                        "name": fn["name"],
                        "input": json.loads(fn["arguments"]) if fn.get("arguments") else {},
                    })
                anthropic_messages.append({"role": "assistant", "content": blocks})
            else:
                anthropic_messages.append({"role": "assistant", "content": content or ""})

        elif role == "tool":
            # tool 结果消息 → Anthropic tool_result 格式
            tool_call_id = msg.get("tool_call_id", "")
            # Anthropic 要求 tool_result 包在 user 消息里
            if anthropic_messages and anthropic_messages[-1]["role"] == "user":
                # 追加到上一条 user 消息
                last = anthropic_messages[-1]
                if isinstance(last["content"], list):
                    last["content"].append({
                        "type": "tool_result",
                        "tool_use_id": tool_call_id,
                        "content": content or "",
                    })
                else:
                    anthropic_messages[-1] = {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": last["content"]},
                            {"type": "tool_result", "tool_use_id": tool_call_id, "content": content or ""},
                        ],
                    }
            else:
                anthropic_messages.append({
                    "role": "user",
                    "content": [{"type": "tool_result", "tool_use_id": tool_call_id, "content": content or ""}],
                })

    return system, anthropic_messages


class AnthropicReactAgent:
    """使用 Anthropic 原生 SDK 的 ReactAgent 兼容实现。"""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-3-5-haiku-20241022",
        tools=None,
        system_prompt: str | None = None,
        session_id: str | None = None,
        max_iterations: int = 10,
        callbacks=None,
        **kwargs,
    ) -> None:
        if not ANTHROPIC_AVAILABLE:
            raise ImportError(
                "请安装 anthropic 包：uv pip install anthropic 或 pip install anthropic"
            )

        import sys
        from pathlib import Path
        sys.path.insert(0, str(Path(__file__).parent.parent))

        from myreactagent import ReactAgent
        from myreactagent.tools.registry import ToolRegistry
        from myreactagent.memory.conversation import ConversationMemory
        from myreactagent.callbacks.base import BaseCallbackHandler
        from myreactagent.schemas.messages import Message

        self.session_id = session_id or str(uuid.uuid4())
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations
        self.model = model
        self._callbacks = callbacks or []
        self._client = _anthropic_sdk.Anthropic(api_key=api_key)

        self._registry = ToolRegistry()
        for t in (tools or []):
            self._registry.register(t)

        self._memory = ConversationMemory()
        if system_prompt:
            self._memory.add(Message(role="system", content=system_prompt))

    def _emit(self, method: str, data: dict, run_id: str) -> None:
        from myreactagent.schemas.events import CallbackEvent
        event = CallbackEvent(
            event=method, data=data, timestamp=_now_iso(),
            session_id=self.session_id, run_id=run_id,
        )
        for cb in self._callbacks:
            try:
                getattr(cb, method)(event)
            except Exception:
                pass

    def run(self, user_message: str) -> str:
        from myreactagent.schemas.messages import Message, ToolCall, ToolCallFunction

        run_id = str(uuid.uuid4())
        self._memory.add(Message(role="user", content=user_message))
        self._emit("on_agent_start", {"user_message": user_message, "system_prompt": self.system_prompt}, run_id)

        tool_schemas = _openai_tools_to_anthropic(self._registry.get_openai_schemas())

        for iteration in range(self.max_iterations):
            messages = self._memory.get_messages()
            openai_dicts = [m.to_openai_dict() for m in messages]
            system, anthropic_msgs = _openai_messages_to_anthropic(openai_dicts)

            self._emit("on_llm_start", {"messages": openai_dicts, "tools": tool_schemas, "stream": False}, run_id)

            kwargs: dict = {"model": self.model, "max_tokens": 4096, "messages": anthropic_msgs}
            if system:
                kwargs["system"] = system
            if tool_schemas:
                kwargs["tools"] = tool_schemas

            response = self._client.messages.create(**kwargs)

            # 解析响应
            final_text = ""
            tool_uses = []
            for block in response.content:
                if block.type == "text":
                    final_text += block.text
                elif block.type == "tool_use":
                    tool_uses.append(block)

            self._emit("on_llm_end", {
                "content": final_text,
                "tool_calls": [{"name": b.name, "id": b.id} for b in tool_uses] or None,
                "finish_reason": response.stop_reason,
            }, run_id)

            if response.stop_reason == "end_turn" or not tool_uses:
                self._memory.add(Message(role="assistant", content=final_text))
                self._emit("on_agent_end", {"final_answer": final_text, "iterations": iteration + 1}, run_id)
                return final_text

            # 执行工具调用
            tc_objs = [
                ToolCall(id=b.id, function=ToolCallFunction(
                    name=b.name, arguments=json.dumps(b.input)
                ))
                for b in tool_uses
            ]
            self._memory.add(Message(role="assistant", content=final_text, tool_calls=tc_objs))

            for b in tool_uses:
                self._emit("on_tool_start", {"tool_name": b.name, "tool_call_id": b.id, "arguments": b.input}, run_id)
                result = self._registry.execute(b.name, b.input, tool_call_id=b.id)
                self._emit("on_tool_end", {
                    "tool_name": b.name, "tool_call_id": b.id,
                    "success": result.success, "result": result.content if result.success else result.error,
                }, run_id)
                self._memory.add(result.to_message())

        # 安全兜底
        self._memory.add(Message(role="user", content="请基于已有信息给出最终答案。"))
        system, anthropic_msgs = _openai_messages_to_anthropic(
            [m.to_openai_dict() for m in self._memory.get_messages()]
        )
        kwargs = {"model": self.model, "max_tokens": 2048, "messages": anthropic_msgs}
        if system:
            kwargs["system"] = system
        final = self._client.messages.create(**kwargs)
        answer = "".join(b.text for b in final.content if b.type == "text")
        self._memory.add(Message(role="assistant", content=answer))
        self._emit("on_agent_end", {"final_answer": answer, "iterations": self.max_iterations}, run_id)
        return answer

    def run_stream(self, user_message: str) -> Iterator[str]:
        """流式输出：最终答案阶段逐 token yield。"""
        from myreactagent.schemas.messages import Message, ToolCall, ToolCallFunction

        run_id = str(uuid.uuid4())
        self._memory.add(Message(role="user", content=user_message))
        self._emit("on_agent_start", {"user_message": user_message, "system_prompt": self.system_prompt}, run_id)

        tool_schemas = _openai_tools_to_anthropic(self._registry.get_openai_schemas())

        for iteration in range(self.max_iterations):
            messages = self._memory.get_messages()
            system, anthropic_msgs = _openai_messages_to_anthropic(
                [m.to_openai_dict() for m in messages]
            )
            self._emit("on_llm_start", {"messages": [], "tools": tool_schemas, "stream": True}, run_id)

            kwargs: dict = {"model": self.model, "max_tokens": 4096, "messages": anthropic_msgs}
            if system:
                kwargs["system"] = system
            if tool_schemas:
                kwargs["tools"] = tool_schemas

            accumulated_text = ""
            tool_uses = []
            stop_reason = None

            with self._client.messages.stream(**kwargs) as stream:
                for event in stream:
                    if hasattr(event, "type"):
                        if event.type == "content_block_delta":
                            if hasattr(event.delta, "text"):
                                accumulated_text += event.delta.text
                        elif event.type == "message_stop":
                            stop_reason = getattr(stream.get_final_message(), "stop_reason", "end_turn")

                final_msg = stream.get_final_message()
                stop_reason = final_msg.stop_reason
                for block in final_msg.content:
                    if block.type == "tool_use":
                        tool_uses.append(block)

            self._emit("on_llm_end", {
                "content": accumulated_text,
                "tool_calls": [{"name": b.name} for b in tool_uses] or None,
                "finish_reason": stop_reason,
            }, run_id)

            if stop_reason == "end_turn" or not tool_uses:
                self._memory.add(Message(role="assistant", content=accumulated_text))
                self._emit("on_agent_end", {"final_answer": accumulated_text, "iterations": iteration + 1}, run_id)
                yield from accumulated_text
                return

            # 执行工具
            tc_objs = [
                ToolCall(id=b.id, function=ToolCallFunction(name=b.name, arguments=json.dumps(b.input)))
                for b in tool_uses
            ]
            self._memory.add(Message(role="assistant", content=accumulated_text, tool_calls=tc_objs))
            for b in tool_uses:
                self._emit("on_tool_start", {"tool_name": b.name, "tool_call_id": b.id, "arguments": b.input}, run_id)
                result = self._registry.execute(b.name, b.input, tool_call_id=b.id)
                self._emit("on_tool_end", {"tool_name": b.name, "tool_call_id": b.id,
                                           "success": result.success, "result": result.content}, run_id)
                self._memory.add(result.to_message())

        # 安全兜底（宪法 XVII / FR-003）：与 run() 对称
        fallback_msg = "请基于已有信息给出最终答案。"
        self._memory.add(Message(role="user", content=fallback_msg))
        system, anthropic_msgs = _openai_messages_to_anthropic(
            [m.to_openai_dict() for m in self._memory.get_messages()]
        )
        self._emit("on_llm_start", {"messages": [], "tools": tool_schemas, "stream": True}, run_id)
        kwargs: dict = {"model": self.model, "max_tokens": 2048, "messages": anthropic_msgs}
        if system:
            kwargs["system"] = system

        final_text = ""
        with self._client.messages.stream(**kwargs) as stream:
            for event in stream:
                if hasattr(event, "type") and event.type == "content_block_delta":
                    if hasattr(event.delta, "text"):
                        final_text += event.delta.text
                        yield event.delta.text

        self._memory.add(Message(role="assistant", content=final_text))
        self._emit("on_llm_end", {"content": final_text, "finish_reason": "end_turn"}, run_id)
        self._emit("on_agent_end", {"final_answer": final_text, "iterations": self.max_iterations}, run_id)
