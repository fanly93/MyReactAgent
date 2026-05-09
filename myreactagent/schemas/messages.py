from __future__ import annotations

from typing import Literal, Union

from pydantic import BaseModel


class TextContentPart(BaseModel):
    type: Literal["text"] = "text"
    text: str


class ImageContentPart(BaseModel):
    # Phase 1 预留，Phase 4 实现序列化
    type: Literal["image_url"] = "image_url"
    image_url: dict


class AudioContentPart(BaseModel):
    # Phase 1 预留，Phase 4 实现序列化
    type: Literal["input_audio"] = "input_audio"
    input_audio: dict


ContentPart = Union[TextContentPart, ImageContentPart, AudioContentPart]
MessageContent = Union[str, list[ContentPart]]


class ToolCallFunction(BaseModel):
    name: str
    arguments: str  # LLM 生成的 JSON 字符串，需调用方解析


class ToolCall(BaseModel):
    id: str
    type: Literal["function"] = "function"
    function: ToolCallFunction


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: MessageContent
    tool_calls: list[ToolCall] | None = None   # role=assistant 携带工具调用请求
    tool_call_id: str | None = None            # role=tool 关联对应的工具调用
    name: str | None = None                    # role=tool 标注工具名称

    def to_openai_dict(self) -> dict:
        """转换为 OpenAI API 兼容的消息字典格式。"""
        if isinstance(self.content, list):
            raise NotImplementedError(
                "list[ContentPart] content is not supported in Phase 1. "
                "Use str content instead. Multi-modal support will be added in Phase 4."
            )

        d: dict = {"role": self.role, "content": self.content}

        if self.tool_calls is not None:
            d["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in self.tool_calls
            ]

        if self.tool_call_id is not None:
            d["tool_call_id"] = self.tool_call_id

        if self.name is not None:
            d["name"] = self.name

        return d
