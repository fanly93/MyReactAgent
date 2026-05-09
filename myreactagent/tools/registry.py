from __future__ import annotations

import json

from pydantic import ValidationError, create_model
from typing import Any

from myreactagent.tools.base import BaseTool
from myreactagent.schemas.tools import ToolResult

# TODO Phase 3: 升级为 token-aware 截断（tiktoken），支持全局默认和工具级覆盖。见 specs/deferred-items.md DI-001
MAX_TOOL_OUTPUT_CHARS = 8000


class ToolRegistry:
    """工具注册中心，负责注册、查找和执行工具。实例变量，非类变量（宪法 XII）。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具到注册表。"""
        self._tools[tool.name] = tool

    def get_tool(self, name: str) -> BaseTool | None:
        """按名称查找工具，不存在时返回 None。"""
        return self._tools.get(name)

    def get_openai_schemas(self) -> list[dict]:
        """返回所有工具的 OpenAI function calling 格式 schema 列表。"""
        schemas = []
        for tool in self._tools.values():
            schemas.append(
                {
                    "type": "function",
                    "function": {
                        "name": tool.name,
                        "description": tool.description,
                        "parameters": tool.parameters_schema,
                    },
                }
            )
        return schemas

    def execute(self, name: str, args: dict, tool_call_id: str = "") -> ToolResult:
        """验证参数并执行指定工具，捕获所有异常转化为失败结果。"""
        tool = self._tools.get(name)
        if tool is None:
            msg = f"Tool '{name}' not found in registry."
            return ToolResult(
                tool_call_id=tool_call_id,
                success=False,
                error=msg,
                error_type="ToolNotFoundError",
                error_message=msg,
            )

        # 用 Pydantic 动态模型验证参数
        schema = tool.parameters_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # 构建 Pydantic 字段定义
        fields: dict[str, Any] = {}
        for field_name, field_schema in properties.items():
            type_map = {
                "string": str,
                "integer": int,
                "number": float,
                "boolean": bool,
                "array": list,
                "object": dict,
            }
            py_type = type_map.get(field_schema.get("type", "string"), str)
            if field_name in required:
                fields[field_name] = (py_type, ...)
            else:
                fields[field_name] = (py_type, None)

        try:
            if fields:
                ArgsModel = create_model("_Args", **fields)
                validated = ArgsModel(**args)
                validated_args = validated.model_dump(exclude_none=False)
                # 只传入 schema 中定义的字段
                filtered_args = {k: v for k, v in validated_args.items() if k in properties}
            else:
                filtered_args = {}

            result = tool.execute(filtered_args)

            # 工具输出长度保护：超出字符上限时截断并通知模型（Phase 1 字符级近似）
            content = result.content
            if isinstance(content, str) and len(content) > MAX_TOOL_OUTPUT_CHARS:
                content = (
                    content[:MAX_TOOL_OUTPUT_CHARS]
                    + f"\n[工具输出过长，已截断至前 {MAX_TOOL_OUTPUT_CHARS} 字符，原始长度 {len(result.content)} 字符]"
                )

            # 填充正确的 tool_call_id
            return ToolResult(
                tool_call_id=tool_call_id,
                success=result.success,
                content=content,
                error=result.error,
            )

        except ValidationError as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                success=False,
                error=f"Parameter validation failed: {e}",
                error_type="ValidationError",
                error_message=str(e),
            )
        except Exception as e:
            return ToolResult(
                tool_call_id=tool_call_id,
                success=False,
                error=f"{type(e).__name__}: {e}",
                error_type=type(e).__name__,
                error_message=str(e),
            )
