from __future__ import annotations

from myreactagent.schemas.events import CallbackEvent


class BaseCallbackHandler:
    """Agent 生命周期回调基类，所有方法默认为空实现，子类按需覆盖。"""

    def on_agent_start(self, event: CallbackEvent) -> None:
        pass

    def on_llm_start(self, event: CallbackEvent) -> None:
        pass

    def on_llm_end(self, event: CallbackEvent) -> None:
        pass

    def on_tool_start(self, event: CallbackEvent) -> None:
        pass

    def on_tool_end(self, event: CallbackEvent) -> None:
        pass

    def on_agent_end(self, event: CallbackEvent) -> None:
        pass

    def on_error(self, event: CallbackEvent) -> None:
        pass
