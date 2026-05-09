from __future__ import annotations

from myreactagent.callbacks.base import BaseCallbackHandler
from myreactagent.schemas.events import CallbackEvent


class ConsoleCallbackHandler(BaseCallbackHandler):
    """开箱即用的控制台输出回调，打印所有 7 类生命周期事件的格式化信息。"""

    def on_agent_start(self, event: CallbackEvent) -> None:
        print(
            f"[{event.timestamp}] 🚀 Agent 启动 | session={event.session_id[:8]}... "
            f"| 输入: {event.data.get('user_message', '')[:80]}"
        )

    def on_llm_start(self, event: CallbackEvent) -> None:
        stream = event.data.get("stream", False)
        tools_count = len(event.data.get("tools", []))
        print(
            f"[{event.timestamp}] 🤔 LLM 请求 | stream={stream} | tools={tools_count}"
        )

    def on_llm_end(self, event: CallbackEvent) -> None:
        finish_reason = event.data.get("finish_reason", "unknown")
        tool_calls = event.data.get("tool_calls")
        content_preview = (event.data.get("content") or "")[:60]
        if tool_calls:
            tool_names = [tc.get("name", "?") for tc in tool_calls]
            print(
                f"[{event.timestamp}] ✅ LLM 完成 | finish={finish_reason} "
                f"| 工具调用: {tool_names}"
            )
        else:
            print(
                f"[{event.timestamp}] ✅ LLM 完成 | finish={finish_reason} "
                f"| 内容: {content_preview!r}"
            )

    def on_tool_start(self, event: CallbackEvent) -> None:
        print(
            f"[{event.timestamp}] 🔧 工具调用 | {event.data.get('tool_name')} "
            f"| id={event.data.get('tool_call_id')} "
            f"| 参数: {event.data.get('arguments')}"
        )

    def on_tool_end(self, event: CallbackEvent) -> None:
        success = event.data.get("success", False)
        status = "✓" if success else "✗"
        if success:
            display = str(event.data.get("result", ""))[:60]
        else:
            error_type = event.data.get("error_type", "Error")
            error_msg = str(event.data.get("error_message", ""))[:60]
            display = f"{error_type}: {error_msg}"
        print(
            f"[{event.timestamp}] {status} 工具结果 | {event.data.get('tool_name')} "
            f"| {display!r}"
        )

    def on_agent_end(self, event: CallbackEvent) -> None:
        iterations = event.data.get("iterations", "?")
        answer_preview = str(event.data.get("final_answer", ""))[:80]
        print(
            f"[{event.timestamp}] 🏁 Agent 完成 | 迭代次数={iterations} "
            f"| 答案: {answer_preview!r}"
        )

    def on_error(self, event: CallbackEvent) -> None:
        print(
            f"[{event.timestamp}] ❌ 错误 | 类型={event.data.get('error_type')} "
            f"| 消息={event.data.get('error_message')} "
            f"| 上下文={event.data.get('context', '')}"
        )
