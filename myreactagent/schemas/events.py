from enum import Enum

from pydantic import BaseModel


class NextStep(Enum):
    """ReAct 循环下一步走向枚举。"""

    STOP = "stop"           # 终止循环，输出最终答案（Phase 1 完整实现）
    CONTINUE = "continue"   # 执行工具后继续循环（Phase 1 完整实现）
    HANDOFF = "handoff"     # 移交至其他 Agent（Phase 2 占位）
    INTERRUPT = "interrupt" # 等待人工确认（Phase 4 占位）


class CallbackEvent(BaseModel):
    """Agent 生命周期事件载荷，贯穿所有阶段保持结构稳定（宪法 VII）。"""

    event: str      # 事件类型名，如 "on_agent_start"
    data: dict      # 事件特定数据，各事件字段见 data-model.md
    timestamp: str  # ISO-8601 格式时间戳
    session_id: str # Agent 实例级别标识
    run_id: str     # 单次 run() 调用级别标识
    span_id: str = ""  # Phase 1 留空，Phase 4 填充 OpenTelemetry span id
