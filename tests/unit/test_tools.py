"""工具装饰器和 BaseTool 单元测试。"""

import pytest
from myreactagent.tools.base import BaseTool
from myreactagent.tools.decorator import tool
from myreactagent.schemas.tools import ToolResult


class TestToolDecorator:
    def test_basic_decorator_no_args(self):
        @tool
        def add(a: int, b: int) -> int:
            """将两个整数相加。"""
            return a + b

        assert add.name == "add"
        assert add.description == "将两个整数相加。"
        assert isinstance(add, BaseTool)

    def test_schema_generation_with_types(self):
        @tool
        def search(query: str, max_results: int) -> str:
            """搜索内容。"""
            return ""

        schema = add.parameters_schema if False else search.parameters_schema
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert schema["properties"]["query"]["type"] == "string"
        assert "max_results" in schema["properties"]
        assert schema["properties"]["max_results"]["type"] == "integer"
        assert "query" in schema["required"]
        assert "max_results" in schema["required"]

    def test_schema_no_type_annotation_defaults_to_string(self):
        @tool
        def greet(name) -> str:  # 无类型注解
            """问候某人。"""
            return f"Hello, {name}"

        schema = greet.parameters_schema
        assert schema["properties"]["name"]["type"] == "string"

    def test_docstring_extraction(self):
        @tool
        def calc(expr: str) -> str:
            """计算数学表达式。

            支持加减乘除。
            """
            return ""

        assert calc.description == "计算数学表达式。"

    def test_missing_docstring_gives_empty_description(self):
        @tool
        def no_doc(x: int) -> int:
            return x

        assert no_doc.description == ""

    def test_parametrized_decorator_is_destructive(self):
        @tool(is_destructive=True, permission="destructive")
        def delete(path: str) -> str:
            """删除文件。"""
            return ""

        assert delete.is_destructive is True
        assert delete.permission == "destructive"

    def test_default_permissions(self):
        @tool
        def safe_read(path: str) -> str:
            """读取文件。"""
            return ""

        assert safe_read.is_destructive is False
        assert safe_read.permission == "read"

    def test_execute_returns_tool_result(self):
        @tool
        def multiply(a: int, b: int) -> int:
            """相乘。"""
            return a * b

        result = multiply.execute({"a": 3, "b": 7})
        assert isinstance(result, ToolResult)
        assert result.success is True
        assert result.content == "21"

    def test_execute_with_default_param(self):
        @tool
        def greet(name: str, greeting: str = "Hello") -> str:
            """问候。"""
            return f"{greeting}, {name}"

        result = greet.execute({"name": "Alice"})
        assert result.success is True
        assert "Alice" in result.content

    def test_no_required_for_params_with_defaults(self):
        @tool
        def func(required: str, optional: int = 0) -> str:
            """测试函数。"""
            return ""

        schema = func.parameters_schema
        assert "required" in schema
        assert "required" in schema["required"]
        assert "optional" not in schema.get("required", [])


class TestBaseTool:
    def test_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseTool()

    def test_concrete_subclass_works(self):
        class MyTool(BaseTool):
            name = "my_tool"
            description = "测试工具"

            @property
            def parameters_schema(self) -> dict:
                return {
                    "type": "object",
                    "properties": {"x": {"type": "integer"}},
                    "required": ["x"],
                }

            def execute(self, args: dict) -> ToolResult:
                return ToolResult(tool_call_id="", success=True, content=str(args["x"] * 2))

        t = MyTool()
        assert t.name == "my_tool"
        assert t.is_destructive is False
        assert t.permission == "read"
        result = t.execute({"x": 5})
        assert result.content == "10"
