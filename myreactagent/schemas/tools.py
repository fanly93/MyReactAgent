from __future__ import annotations

from pydantic import BaseModel

from myreactagent.schemas.messages import Message, MessageContent


class ToolResult(BaseModel):
    """工具执行结果，统一封装成功与失败两种情况。"""

    tool_call_id: str
    success: bool
    content: MessageContent = ""   # 成功时的返回内容，Phase 1 仅使用 str 分支
    error: str | None = None       # 失败时的合并错误描述（用于 LLM 消息）
    error_type: str | None = None  # 失败时的异常类名（用于 on_tool_end 载荷）
    error_message: str | None = None  # 失败时的异常消息（用于 on_tool_end 载荷）

    def to_message(self) -> Message:
        """转换为 role='tool' 的消息，用于加入对话历史。"""
        if isinstance(self.content, list):
            content_str = self.error or "error"
        elif self.content:  # 非空字符串
            content_str = self.content
        else:  # 空字符串（默认值），回退到 error 字段
            content_str = self.error or "error"
        return Message(
            role="tool",
            tool_call_id=self.tool_call_id,
            content=content_str,
        )
