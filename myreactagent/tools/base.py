from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Literal

from myreactagent.schemas.tools import ToolResult


class BaseTool(ABC):
    """工具抽象基类，所有工具必须继承此类。"""

    name: str
    description: str
    is_destructive: bool = False
    permission: Literal["read", "write", "destructive"] = "read"

    @property
    @abstractmethod
    def parameters_schema(self) -> dict:
        """返回符合 JSON Schema 规范的参数描述（type: object）。"""

    @abstractmethod
    def execute(self, args: dict) -> ToolResult:
        """执行工具逻辑，框架在调用前已完成参数验证。"""
