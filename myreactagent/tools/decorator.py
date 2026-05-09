from __future__ import annotations

import inspect
from typing import Any, Callable, Literal, get_type_hints

from pydantic import create_model

from myreactagent.tools.base import BaseTool
from myreactagent.schemas.tools import ToolResult

# Python 类型到 JSON Schema 类型的映射
_TYPE_MAP: dict[type, str] = {
    str: "string",
    int: "integer",
    float: "number",
    bool: "boolean",
    list: "array",
    dict: "object",
}


def _build_parameters_schema(func: Callable) -> dict:
    """从函数签名和类型注解生成 OpenAI function calling 格式的 JSON Schema。"""
    try:
        hints = get_type_hints(func)
    except Exception:
        hints = {}

    hints.pop("return", None)

    sig = inspect.signature(func)
    properties: dict[str, dict] = {}
    required: list[str] = []

    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue

        py_type = hints.get(param_name, str)
        json_type = _TYPE_MAP.get(py_type, "string")
        properties[param_name] = {"type": json_type}

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema = {"type": "object", "properties": properties}
    if required:
        schema["required"] = required
    return schema


def _make_tool_class(
    func: Callable,
    is_destructive: bool,
    permission: Literal["read", "write", "destructive"],
) -> BaseTool:
    """将普通函数包装为 BaseTool 子类实例。"""
    tool_name = func.__name__
    doc = inspect.getdoc(func) or ""
    tool_description = doc.splitlines()[0].strip() if doc else ""
    schema = _build_parameters_schema(func)

    # 动态构建 Pydantic 模型用于参数验证
    hints = get_type_hints(func)
    hints.pop("return", None)
    sig = inspect.signature(func)

    fields: dict[str, Any] = {}
    for param_name, param in sig.parameters.items():
        if param_name == "self":
            continue
        py_type = hints.get(param_name, str)
        if param.default is inspect.Parameter.empty:
            fields[param_name] = (py_type, ...)
        else:
            fields[param_name] = (py_type, param.default)

    ArgsModel = create_model(f"{tool_name}_args", **fields) if fields else create_model(f"{tool_name}_args")

    _is_destructive = is_destructive
    _permission = permission

    class FunctionTool(BaseTool):
        name = tool_name
        description = tool_description
        is_destructive = _is_destructive
        permission = _permission

        @property
        def parameters_schema(self) -> dict:
            return schema

        def execute(self, args: dict) -> ToolResult:
            # tool_call_id 由框架注入，执行前移除
            args = {k: v for k, v in args.items() if k != "_tool_call_id"}
            validated = ArgsModel(**args)
            result = func(**validated.model_dump())
            content = str(result) if result is not None else ""
            # tool_call_id 在 ToolRegistry.execute 中填充
            return ToolResult(tool_call_id="", success=True, content=content)

    instance = FunctionTool()
    return instance


def tool(
    func: Callable | None = None,
    *,
    is_destructive: bool = False,
    permission: Literal["read", "write", "destructive"] = "read",
) -> Any:
    """将函数转换为 BaseTool 实例的装饰器。

    用法一（无参数）::

        @tool
        def add(a: int, b: int) -> int:
            \"\"\"将两个整数相加。\"\"\"
            return a + b

    用法二（带参数）::

        @tool(is_destructive=True, permission="destructive")
        def delete_file(path: str) -> str:
            \"\"\"删除指定文件。\"\"\"
            ...
    """
    if func is not None:
        # @tool 无参数形式：直接传入函数
        return _make_tool_class(func, is_destructive=False, permission="read")

    # @tool(...) 带参数形式：返回装饰器
    def decorator(f: Callable) -> BaseTool:
        return _make_tool_class(f, is_destructive=is_destructive, permission=permission)

    return decorator
