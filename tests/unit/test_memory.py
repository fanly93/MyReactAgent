"""ConversationMemory 截断算法单元测试（T020）。"""

import pytest
from myreactagent.memory.conversation import ConversationMemory
from myreactagent.schemas.messages import Message, ToolCall, ToolCallFunction


def _user(content: str) -> Message:
    return Message(role="user", content=content)


def _assistant(content: str, with_tool_calls: bool = False) -> Message:
    if with_tool_calls:
        tc = ToolCall(id="call_x", function=ToolCallFunction(name="t", arguments="{}"))
        return Message(role="assistant", content=content, tool_calls=[tc])
    return Message(role="assistant", content=content)


def _tool(content: str = "result") -> Message:
    return Message(role="tool", content=content, tool_call_id="call_x")


def _system(content: str = "系统提示") -> Message:
    return Message(role="system", content=content)


class TestConversationMemoryBasic:
    def test_add_and_get(self):
        mem = ConversationMemory()
        mem.add(_user("hello"))
        msgs = mem.get_messages()
        assert len(msgs) == 1
        assert msgs[0].content == "hello"

    def test_get_returns_copy(self):
        mem = ConversationMemory()
        mem.add(_user("test"))
        msgs = mem.get_messages()
        msgs.clear()
        assert len(mem.get_messages()) == 1

    def test_clear(self):
        mem = ConversationMemory()
        mem.add(_user("msg"))
        mem.clear()
        assert mem.get_messages() == []


class TestConversationMemoryTruncation:
    def test_no_truncation_when_under_limit(self):
        mem = ConversationMemory(max_messages=10, keep_last_n=3)
        for i in range(5):
            mem.add(_user(f"用户 {i}"))
            mem.add(_assistant(f"助手 {i}"))
        assert len(mem.get_messages()) == 10

    def test_truncates_oldest_messages(self):
        mem = ConversationMemory(max_messages=4, keep_last_n=1)
        # 添加 6 条消息，应截断到 4 条
        for i in range(3):
            mem.add(_user(f"用户 {i}"))
            mem.add(_assistant(f"助手 {i}"))

        msgs = mem.get_messages()
        assert len(msgs) <= 4

    def test_system_message_never_removed(self):
        mem = ConversationMemory(max_messages=4, keep_last_n=1)
        mem.add(_system("重要系统提示"))
        # 添加大量普通消息
        for i in range(10):
            mem.add(_user(f"用户 {i}"))
            mem.add(_assistant(f"助手 {i}"))

        msgs = mem.get_messages()
        system_msgs = [m for m in msgs if m.role == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0].content == "重要系统提示"

    def test_tool_call_pair_not_split(self):
        """assistant（含 tool_calls）和紧随的 tool 消息是原子对，不得拆开。"""
        mem = ConversationMemory(max_messages=6, keep_last_n=2)
        # 填充一些普通消息
        for i in range(3):
            mem.add(_user(f"早期问题 {i}"))
            mem.add(_assistant(f"早期回答 {i}"))

        # 添加工具调用对（原子保护）
        mem.add(_user("计算"))
        mem.add(_assistant("", with_tool_calls=True))
        mem.add(_tool("42"))
        mem.add(_assistant("结果是 42"))

        msgs = mem.get_messages()
        roles = [m.role for m in msgs]

        # 不能出现 tool 消息而没有前置 assistant(tool_calls) 消息
        for idx, msg in enumerate(msgs):
            if msg.role == "tool":
                assert idx > 0
                assert msgs[idx - 1].role == "assistant"

    def test_keep_last_n_rounds_protected(self):
        mem = ConversationMemory(max_messages=6, keep_last_n=3)
        # 添加 5 轮对话（10 条消息），只保护最近 3 轮
        contents = []
        for i in range(5):
            mem.add(_user(f"问题{i}"))
            mem.add(_assistant(f"回答{i}"))
            contents.append((f"问题{i}", f"回答{i}"))

        msgs = mem.get_messages()
        msg_contents = [m.content for m in msgs]

        # 最近的消息应该被保留
        assert "问题4" in msg_contents
        assert "回答4" in msg_contents
        assert "问题3" in msg_contents
        assert "回答3" in msg_contents

    def test_message_count_respects_max(self):
        mem = ConversationMemory(max_messages=6, keep_last_n=2)
        for i in range(20):
            mem.add(_user(f"q{i}"))
            mem.add(_assistant(f"a{i}"))

        non_system = [m for m in mem.get_messages() if m.role != "system"]
        assert len(non_system) <= 6
