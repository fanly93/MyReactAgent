from __future__ import annotations

from myreactagent.schemas.messages import Message


# TODO Phase 3: 升级为 token-aware 截断（tiktoken），新增 summarize 策略。见 specs/deferred-items.md DI-002
class ConversationMemory:
    """对话历史管理，内置滑动窗口截断策略（宪法 XIII）。"""

    def __init__(
        self,
        max_messages: int = 20,
        keep_last_n: int = 6,
    ) -> None:
        self.max_messages = max_messages
        self.keep_last_n = keep_last_n  # 保护最近 N 轮完整对话
        self._messages: list[Message] = []
        self._last_add_overflowed: bool = False  # FR-007b: 原子对是否溢出 max_messages

    def add(self, message: Message) -> None:
        """添加消息到历史，添加后触发截断检查。"""
        self._messages.append(message)
        self._truncate()

    def get_messages(self) -> list[Message]:
        """返回当前消息列表（已完成截断处理）。"""
        return list(self._messages)

    def clear(self) -> None:
        """清空所有消息历史。"""
        self._messages = []

    @property
    def last_add_overflowed(self) -> bool:
        """上次 add() 后原子对保护是否导致消息数超出 max_messages（FR-007b）。"""
        return self._last_add_overflowed

    def _truncate(self) -> None:
        """滑动窗口截断算法，保护 system 消息、tool_call 配对和最近 N 轮对话。

        保护规则（宪法 XIII）：
        1. role=system 消息永远保留，不计入截断窗口
        2. assistant（含 tool_calls）+ 其后所有 tool 消息为原子对，不拆开
        3. 最近 keep_last_n 轮完整对话（user+assistant）保护
        4. 仅截断保护区外的中间普通消息
        """
        # 非 system 消息数量未超限则无需截断
        non_system = [m for m in self._messages if m.role != "system"]
        if len(non_system) <= self.max_messages:
            self._last_add_overflowed = False
            return

        system_msgs = [m for m in self._messages if m.role == "system"]
        non_system_msgs = [m for m in self._messages if m.role != "system"]

        # 找出最近 keep_last_n 轮（每轮：user + assistant 应答，含工具调用链）的保护范围
        protected_tail = self._find_protected_tail(non_system_msgs)

        # FR-007b: 原子对本身超过 max_messages 上限，标记溢出；原子对仍完整保留
        self._last_add_overflowed = protected_tail > self.max_messages

        # 中间可截断区间
        truncatable = non_system_msgs[: len(non_system_msgs) - protected_tail]

        # 逐条移除最旧的非保护消息，直到满足 max_messages
        while len(truncatable) + protected_tail > self.max_messages and truncatable:
            truncatable.pop(0)

        self._messages = system_msgs + truncatable + non_system_msgs[len(non_system_msgs) - protected_tail :]

    def _find_protected_tail(self, msgs: list[Message]) -> int:
        """从末尾向前计算需要保护的消息数（最近 keep_last_n 轮 + 原子对保护）。"""
        if not msgs:
            return 0

        rounds = 0
        idx = len(msgs) - 1
        protected_count = 0

        while idx >= 0 and rounds < self.keep_last_n:
            msg = msgs[idx]

            if msg.role == "assistant":
                # 向前检查是否有关联的 tool 消息（原子对）
                protected_count += 1
                idx -= 1
                rounds += 1
            elif msg.role == "tool":
                # tool 消息属于 assistant 原子对的一部分，继续向前追溯
                protected_count += 1
                idx -= 1
            elif msg.role == "user":
                protected_count += 1
                idx -= 1
            else:
                idx -= 1

        return protected_count
