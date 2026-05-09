from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Iterator

from myreactagent.callbacks.base import BaseCallbackHandler
from myreactagent.llm.client import LLMClient
from myreactagent.memory.conversation import ConversationMemory
from myreactagent.schemas.events import CallbackEvent, NextStep
from myreactagent.schemas.messages import Message, ToolCall, ToolCallFunction
from myreactagent.schemas.tools import ToolResult
from myreactagent.tools.base import BaseTool
from myreactagent.tools.registry import ToolRegistry


_MAX_SYSTEM_PROMPT_CHARS = 8000  # Phase 1 字符级阈值；Phase 3 升级为 token-aware


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


class ReactAgent:
    """ReAct Agent：Reasoning + Acting 循环框架核心实现。"""

    def __init__(
        self,
        tools: list[BaseTool] | None = None,
        system_prompt: str | None = None,
        session_id: str | None = None,
        max_iterations: int = 10,
        max_messages: int = 20,
        keep_last_n: int = 6,
        callbacks: list[BaseCallbackHandler] | None = None,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        self.session_id = session_id or str(uuid.uuid4())
        self.system_prompt = system_prompt
        self.max_iterations = max_iterations

        self._memory = ConversationMemory(max_messages=max_messages, keep_last_n=keep_last_n)
        self._tools = ToolRegistry()
        self._llm = LLMClient(model=model, base_url=base_url, api_key=api_key)
        self._callbacks: list[BaseCallbackHandler] = callbacks or []
        self._system_prompt_warning_emitted = False  # MC-002: 每个实例只发一次 warning

        for t in (tools or []):
            self._tools.register(t)

        if system_prompt:
            self._memory.add(Message(role="system", content=system_prompt))

    # ── 核心辅助方法 ────────────────────────────────────────────────────────────

    def _emit(self, method_name: str, data: dict, run_id: str) -> None:
        """分发生命周期事件到所有回调处理器，单个回调抛出异常不中断主流程。"""
        event = CallbackEvent(
            event=method_name,
            data=data,
            timestamp=_now_iso(),
            session_id=self.session_id,
            run_id=run_id,
        )
        for cb in self._callbacks:
            try:
                getattr(cb, method_name)(event)
            except Exception:
                pass

    def _check_system_prompt_length(self, run_id: str) -> None:
        """MC-002: 系统提示超长时发出一次 on_error warning（Edge Cases）。"""
        if (
            self.system_prompt
            and len(self.system_prompt) > _MAX_SYSTEM_PROMPT_CHARS
            and not self._system_prompt_warning_emitted
        ):
            self._emit(
                "on_error",
                {
                    "warning": True,
                    "error_type": "SystemPromptTooLong",
                    "error_message": (
                        f"系统提示长度（{len(self.system_prompt)} 字符）"
                        f"超过 {_MAX_SYSTEM_PROMPT_CHARS} 字符阈值，"
                        "可能导致接近模型上下文上限。"
                    ),
                },
                run_id,
            )
            self._system_prompt_warning_emitted = True

    def _emit_overflow_warning(self, run_id: str) -> None:
        """FR-007b: 发出原子对溢出 on_error warning（调用方负责判断是否触发）。"""
        self._emit(
            "on_error",
            {
                "warning": True,
                "error_type": "ContextOverflow",
                "error_message": (
                    f"tool_call 原子对消息数超出 max_messages={self._memory.max_messages} 上限，"
                    "原子对已完整保留，实际消息数暂时超出上限。"
                ),
            },
            run_id,
        )

    def _get_tool_schemas(self) -> list[dict]:
        return self._tools.get_openai_schemas()

    def _execute_tool_calls(
        self, tool_calls: list, run_id: str
    ) -> list[Message]:
        """执行一组工具调用，返回 role=tool 的消息列表。"""
        tool_messages: list[Message] = []
        for tc in tool_calls:
            tool_name = tc.function.name
            tool_call_id = tc.id
            raw_args = tc.function.arguments

            # 解析 JSON 参数
            try:
                args = json.loads(raw_args) if raw_args else {}
            except json.JSONDecodeError as e:
                self._emit(
                    "on_error",
                    {
                        "error_type": "JSONDecodeError",
                        "error_message": str(e),
                        "context": f"Failed to parse tool call arguments for '{tool_name}'",
                    },
                    run_id,
                )
                result = ToolResult(
                    tool_call_id=tool_call_id,
                    success=False,
                    error=f"Invalid JSON arguments: {e}",
                )
                tool_messages.append(result.to_message())
                continue

            self._emit(
                "on_tool_start",
                {"tool_name": tool_name, "tool_call_id": tool_call_id, "arguments": args},
                run_id,
            )

            result = self._tools.execute(tool_name, args, tool_call_id=tool_call_id)

            self._emit(
                "on_tool_end",
                {
                    "tool_name": tool_name,
                    "tool_call_id": tool_call_id,
                    "success": result.success,
                    "result": result.content if result.success else None,
                    "error_type": result.error_type if not result.success else None,
                    "error_message": result.error_message if not result.success else None,
                },
                run_id,
            )
            tool_messages.append(result.to_message())

        return tool_messages

    def _decide_next_step(self, finish_reason: str) -> NextStep:
        """根据 LLM finish_reason 决定循环走向。"""
        if finish_reason == "stop":
            return NextStep.STOP
        if finish_reason == "tool_calls":
            return NextStep.CONTINUE
        # 其他情况（如 length）视为 STOP
        return NextStep.STOP
        # TODO Phase 2: 返回 NextStep.HANDOFF（子 Agent 移交）。见 specs/deferred-items.md DI-006
        # TODO Phase 4: 返回 NextStep.INTERRUPT（人工确认）。见 specs/deferred-items.md DI-006

    # ── 公共 API ────────────────────────────────────────────────────────────────

    def run(self, user_message: str) -> str:
        """同步执行完整的 ReAct 循环，返回最终答案字符串。"""
        run_id = str(uuid.uuid4())
        tool_schemas = self._get_tool_schemas()

        self._check_system_prompt_length(run_id)
        self._memory.add(Message(role="user", content=user_message))

        self._emit(
            "on_agent_start",
            {"user_message": user_message, "system_prompt": self.system_prompt},
            run_id,
        )

        for iteration in range(self.max_iterations):
            messages = self._memory.get_messages()

            self._emit(
                "on_llm_start",
                {"messages": [m.to_openai_dict() for m in messages], "tools": tool_schemas, "stream": False},
                run_id,
            )

            response = self._llm.chat(messages, tools=tool_schemas or None)
            choice = response.choices[0]

            self._emit(
                "on_llm_end",
                {
                    "content": choice.message.content,
                    "tool_calls": (
                        [
                            {"id": tc.id, "name": tc.function.name, "arguments": tc.function.arguments}
                            for tc in choice.message.tool_calls
                        ]
                        if choice.message.tool_calls
                        else None
                    ),
                    "finish_reason": choice.finish_reason,
                },
                run_id,
            )

            next_step = self._decide_next_step(choice.finish_reason)

            if next_step == NextStep.STOP:
                final_answer = choice.message.content or ""
                self._memory.add(Message(role="assistant", content=final_answer))
                self._emit(
                    "on_agent_end",
                    {"final_answer": final_answer, "iterations": iteration + 1},
                    run_id,
                )
                return final_answer

            if next_step in (NextStep.HANDOFF, NextStep.INTERRUPT):
                # 占位实现（FR-021）：Phase 1 不支持，明确抛出异常
                raise NotImplementedError(
                    f"NextStep.{next_step.name} is not implemented until "
                    f"{'Phase 2' if next_step == NextStep.HANDOFF else 'Phase 4'}"
                )

            if next_step == NextStep.CONTINUE:
                # 构建含 tool_calls 的 assistant 消息
                raw_tcs = choice.message.tool_calls or []
                tool_call_objs = [
                    ToolCall(
                        id=tc.id,
                        function=ToolCallFunction(
                            name=tc.function.name,
                            arguments=tc.function.arguments,
                        ),
                    )
                    for tc in raw_tcs
                ]
                assistant_msg = Message(
                    role="assistant",
                    content=choice.message.content or "",
                    tool_calls=tool_call_objs,
                )
                self._memory.add(assistant_msg)
                overflowed = self._memory.last_add_overflowed

                # 执行所有工具调用并添加结果
                tool_messages = self._execute_tool_calls(raw_tcs, run_id)
                for tm in tool_messages:
                    self._memory.add(tm)
                    overflowed = overflowed or self._memory.last_add_overflowed

                # FR-007b: 原子对溢出 warning
                if overflowed:
                    self._emit_overflow_warning(run_id)

        # 安全兜底（宪法 XVII）：达到 max_iterations，追加消息后再调一次 LLM
        self._memory.add(
            Message(
                role="user",
                content="你已达到最大步骤数，请基于当前已有信息给出最终答案。",
            )
        )
        messages = self._memory.get_messages()
        self._emit(
            "on_llm_start",
            {"messages": [m.to_openai_dict() for m in messages], "tools": tool_schemas, "stream": False},
            run_id,
        )

        final_response = self._llm.chat(messages, tools=None)
        final_answer = final_response.choices[0].message.content or ""

        self._emit(
            "on_llm_end",
            {
                "content": final_answer,
                "tool_calls": None,
                "finish_reason": final_response.choices[0].finish_reason,
            },
            run_id,
        )
        self._memory.add(Message(role="assistant", content=final_answer))
        self._emit(
            "on_agent_end",
            {"final_answer": final_answer, "iterations": self.max_iterations},
            run_id,
        )
        return final_answer

    def run_stream(self, user_message: str) -> Iterator[str]:
        """同步流式执行，最终答案阶段逐 token yield，工具调用阶段后台同步执行。"""
        run_id = str(uuid.uuid4())
        tool_schemas = self._get_tool_schemas()

        self._check_system_prompt_length(run_id)
        self._memory.add(Message(role="user", content=user_message))

        self._emit(
            "on_agent_start",
            {"user_message": user_message, "system_prompt": self.system_prompt},
            run_id,
        )

        for iteration in range(self.max_iterations):
            messages = self._memory.get_messages()

            self._emit(
                "on_llm_start",
                {"messages": [m.to_openai_dict() for m in messages], "tools": tool_schemas, "stream": True},
                run_id,
            )

            stream = self._llm.chat_stream(messages, tools=tool_schemas or None)

            # 按 index 累积重建 tool_calls delta
            accumulated_tool_calls: dict[int, dict] = {}
            accumulated_content = ""
            finish_reason = None

            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                finish_reason = chunk.choices[0].finish_reason or finish_reason

                # 累积文字 token
                if delta.content:
                    accumulated_content += delta.content

                # 累积 tool_calls delta（按 index 组装）
                if delta.tool_calls:
                    for tc_delta in delta.tool_calls:
                        idx = tc_delta.index
                        if idx not in accumulated_tool_calls:
                            accumulated_tool_calls[idx] = {
                                "id": "",
                                "name": "",
                                "arguments": "",
                            }
                        if tc_delta.id:
                            accumulated_tool_calls[idx]["id"] = tc_delta.id
                        if tc_delta.function and tc_delta.function.name:
                            accumulated_tool_calls[idx]["name"] = tc_delta.function.name
                        if tc_delta.function and tc_delta.function.arguments:
                            accumulated_tool_calls[idx]["arguments"] += tc_delta.function.arguments

            self._emit(
                "on_llm_end",
                {
                    "content": accumulated_content or None,
                    "tool_calls": list(accumulated_tool_calls.values()) if accumulated_tool_calls else None,
                    "finish_reason": finish_reason,
                },
                run_id,
            )

            if finish_reason == "tool_calls" and accumulated_tool_calls:
                # 构建 tool_call 对象列表
                tool_call_objs = [
                    ToolCall(
                        id=tc["id"],
                        function=ToolCallFunction(name=tc["name"], arguments=tc["arguments"]),
                    )
                    for tc in accumulated_tool_calls.values()
                ]
                assistant_msg = Message(
                    role="assistant",
                    content=accumulated_content,
                    tool_calls=tool_call_objs,
                )
                self._memory.add(assistant_msg)
                overflowed = self._memory.last_add_overflowed

                # 构建 raw tool_call mock 对象供 _execute_tool_calls 使用
                class _RawTC:
                    def __init__(self, id_: str, name: str, arguments: str):
                        self.id = id_
                        self.function = type("F", (), {"name": name, "arguments": arguments})()

                raw_tcs = [
                    _RawTC(tc["id"], tc["name"], tc["arguments"])
                    for tc in accumulated_tool_calls.values()
                ]
                tool_messages = self._execute_tool_calls(raw_tcs, run_id)
                for tm in tool_messages:
                    self._memory.add(tm)
                    overflowed = overflowed or self._memory.last_add_overflowed

                # FR-007b: 原子对溢出 warning
                if overflowed:
                    self._emit_overflow_warning(run_id)
                continue

            # finish_reason == "stop"：逐 token yield 最终答案
            self._memory.add(Message(role="assistant", content=accumulated_content))
            self._emit(
                "on_agent_end",
                {"final_answer": accumulated_content, "iterations": iteration + 1},
                run_id,
            )
            yield from accumulated_content
            return

        # 安全兜底
        self._memory.add(
            Message(role="user", content="你已达到最大步骤数，请基于当前已有信息给出最终答案。")
        )
        messages = self._memory.get_messages()
        self._emit(
            "on_llm_start",
            {"messages": [m.to_openai_dict() for m in messages], "tools": [], "stream": True},
            run_id,
        )
        stream = self._llm.chat_stream(messages, tools=None)
        final_content = ""
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                token = chunk.choices[0].delta.content
                final_content += token
                yield token

        self._emit(
            "on_llm_end",
            {"content": final_content, "tool_calls": None, "finish_reason": "stop"},
            run_id,
        )
        self._memory.add(Message(role="assistant", content=final_content))
        self._emit(
            "on_agent_end",
            {"final_answer": final_content, "iterations": self.max_iterations},
            run_id,
        )
