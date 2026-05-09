"""ToolRegistry 单元测试。"""

import pytest
from myreactagent.tools.decorator import tool
from myreactagent.tools.registry import ToolRegistry
from myreactagent.tools.base import BaseTool
from myreactagent.schemas.tools import ToolResult


@tool
def add(a: int, b: int) -> int:
    """将两个整数相加。"""
    return a + b


@tool
def greet(name: str) -> str:
    """问候某人。"""
    return f"Hello, {name}"


@tool
def fail_tool(x: str) -> str:
    """总是抛出异常的工具。"""
    raise ValueError("故意失败")


class TestToolRegistry:
    def setup_method(self):
        self.registry = ToolRegistry()

    def test_register_and_get(self):
        self.registry.register(add)
        found = self.registry.get_tool("add")
        assert found is add

    def test_get_nonexistent_tool(self):
        assert self.registry.get_tool("nonexistent") is None

    def test_registry_is_instance_variable(self):
        # 验证两个独立实例的注册表完全隔离（宪法 XII）
        r1 = ToolRegistry()
        r2 = ToolRegistry()
        r1.register(add)
        assert r2.get_tool("add") is None

    def test_get_openai_schemas_format(self):
        self.registry.register(add)
        schemas = self.registry.get_openai_schemas()
        assert len(schemas) == 1
        s = schemas[0]
        assert s["type"] == "function"
        assert s["function"]["name"] == "add"
        assert s["function"]["description"] == "将两个整数相加。"
        assert "parameters" in s["function"]
        assert s["function"]["parameters"]["type"] == "object"
        assert "a" in s["function"]["parameters"]["properties"]
        assert "b" in s["function"]["parameters"]["properties"]

    def test_get_openai_schemas_multiple_tools(self):
        self.registry.register(add)
        self.registry.register(greet)
        schemas = self.registry.get_openai_schemas()
        assert len(schemas) == 2
        names = {s["function"]["name"] for s in schemas}
        assert names == {"add", "greet"}

    def test_execute_success(self):
        self.registry.register(add)
        result = self.registry.execute("add", {"a": 3, "b": 4}, tool_call_id="call_1")
        assert result.success is True
        assert result.tool_call_id == "call_1"
        assert result.content == "7"

    def test_execute_tool_not_found(self):
        result = self.registry.execute("nonexistent", {}, tool_call_id="call_x")
        assert result.success is False
        assert "not found" in result.error.lower()
        assert result.error_type == "ToolNotFoundError"
        assert result.error_message is not None

    def test_execute_validation_failure(self):
        self.registry.register(add)
        # 传入错误类型
        result = self.registry.execute("add", {"a": "not_int", "b": 4}, tool_call_id="call_2")
        assert result.success is False
        assert result.error is not None
        assert result.error_type == "ValidationError"
        assert result.error_message is not None

    def test_execute_missing_required_param(self):
        self.registry.register(add)
        result = self.registry.execute("add", {"a": 1}, tool_call_id="call_3")
        assert result.success is False

    def test_execute_tool_exception_captured(self):
        self.registry.register(fail_tool)
        result = self.registry.execute("fail_tool", {"x": "test"}, tool_call_id="call_4")
        assert result.success is False
        assert "ValueError" in result.error or "故意失败" in result.error
        assert result.error_type == "ValueError"
        assert "故意失败" in result.error_message

    def test_execute_preserves_tool_call_id(self):
        self.registry.register(greet)
        result = self.registry.execute("greet", {"name": "Bob"}, tool_call_id="call_999")
        assert result.tool_call_id == "call_999"
