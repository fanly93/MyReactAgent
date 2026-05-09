# 多模态输入实现方案分析

**创建日期**：2026-05-08  
**适用阶段**：Phase 1（schema 设计预留）/ Phase 4（完整实现）  
**关联文档**：`specs/001-phase1-mvp-prototype/spec.md`、`.specify/memory/constitution.md`（Principle XVI）

---

## 一、背景与动机

主流 LLM（GPT-4o、Claude 3.5、Gemini 1.5）均已支持图像、音频等非文本输入。MyReactAgent 在 Phase 1 仅实现文本对话，但**消息数据模型的 `content` 字段类型**需要从 Phase 1 开始设计为可扩展结构，否则 Phase 4 引入多模态时将面临破坏性变更。

宪法 Principle XVI 已明确要求：
> The message schema MUST be designed from Phase 1 to accommodate `content` as either a string or a list of typed content parts, so multimodal can be added without breaking existing callers.

---

## 二、主流框架实现对比

### 2.1 消息 content 字段类型对比

| 框架 | content 字段类型 | 类型安全 | 参考文件 |
|------|----------------|---------|---------|
| **LangChain** | `str \| list[str \| dict]`，配套 TypedDict ContentBlock | ✅ 强（TypedDict + Literal 鉴别器） | `langchain_core/messages/base.py:103`、`messages/content.py:207-849` |
| **openai-agents-python** | `str \| list[dict]`（运行时字典） | ⚠️ 弱（dict，无类型约束） | `models/chatcmpl_converter.py:330-456` |
| **Google ADK** | `types.Content` + `list[types.Part]`（类层次） | ✅ 强（专属数据类） | `adk-python/src/google/adk/types.py` |
| **hermes-agent** | `str \| list[dict]`（运行时字典） | ⚠️ 弱（dict） | `hermes_state.py:1236` |

### 2.2 LangChain ContentBlock 详细结构（推荐参考）

LangChain 采用 TypedDict + Literal 鉴别器模式，在 `langchain_core/messages/content.py` 中定义了多种内容块类型：

```python
# content.py:207 - 文本块
class TextContentBlock(TypedDict):
    type: Literal["text"]
    text: str
    id: NotRequired[str]
    index: NotRequired[int | str]       # 流式场景中的顺序索引
    extras: NotRequired[dict[str, Any]] # 提供商特定元数据

# content.py:498 - 图像块
class ImageContentBlock(TypedDict):
    type: Literal["image_url"]
    image_url: ImageURL

class ImageURL(TypedDict):
    url: str          # 支持 https:// URL 或 data:image/...;base64,...
    detail: NotRequired[Literal["auto", "low", "high"]]  # 分析细度

# content.py:600 - 音频块
class AudioContentBlock(TypedDict):
    type: Literal["audio"]
    audio_url: NotRequired[AudioURL]
    input_audio: NotRequired[InputAudio]

# content.py:549 - 视频块
class VideoContentBlock(TypedDict):
    type: Literal["video_url"]
    video_url: VideoURL
```

**BaseMessage 核心定义（base.py:93-103）：**

```python
class BaseMessage(Serializable):
    content: str | list[str | dict]   # Phase 4 具体化为 str | list[ContentBlock]
```

### 2.3 OpenAI Responses API 格式转换（openai-agents-python）

openai-agents 在 `chatcmpl_converter.py:347-441` 中，将 `list[dict]` 格式的 content 转换为 Responses API 格式：

```python
# chatcmpl_converter.py:347 - 图像处理
if content_type == "image_url":
    image_payload = content_part.get("image_url")
    image_url = image_payload.get("url")
    normalized = {"type": "input_image", "image_url": image_url}

# chatcmpl_converter.py:416 - 音频处理
elif content_part.get("type") == "input_audio":
    audio_payload = casted_audio_param.get("input_audio")
    # 要求：data（base64）+ format（mp3/wav 等）同时存在
    normalized = {"type": "input_audio", "input_audio": {"data": ..., "format": ...}}
```

**关键差异**：openai-agents 图像**仅支持 URL**，不支持 base64 直传（`chatcmpl_converter.py:352`）。

### 2.4 图像传递方式对比

| 框架 | URL | Base64 | 文件路径 | Files API |
|------|-----|--------|---------|----------|
| LangChain | ✅ | ✅ | ✅（转 base64）| ✅（file_id） |
| openai-agents | ✅ | ❌ | ❌ | ❌ |
| Google ADK | ❌ | ✅（blob）| ❌ | ❌ |
| hermes-agent | ✅ | ✅ | ❌ | ❌ |

---

## 三、MyReactAgent 设计方案

### 3.1 设计原则

1. **Phase 1 只预留类型，不实现多模态处理逻辑**：所有代码路径仍只处理 `str` 分支
2. **参考 LangChain 的 TypedDict + Literal 鉴别器模式**：类型安全，IDE 友好，运行时开销极低
3. **兼容 OpenAI Chat Completions API 格式**：content 列表格式直接对应 API 规范
4. **向前兼容**：Phase 1 传入 `str` 的调用方，在 Phase 4 无需修改任何代码

### 3.2 Phase 1 必须实现的 Schema 设计

**文件位置**：`src/react_agent/schema.py`

```python
from __future__ import annotations
from abc import ABC
from typing import Literal, Union, NotRequired
from typing_extensions import TypedDict
from pydantic import BaseModel

# ── 多模态内容块（Phase 1 仅定义类型，Phase 4 实现具体处理）──────────────

class TextContentPart(TypedDict):
    """纯文本内容块，Phase 1 唯一实际使用的类型。"""
    type: Literal["text"]
    text: str

class ImageContentPart(TypedDict):
    """图像内容块（Phase 4 实现）。"""
    type: Literal["image_url"]
    image_url: ImageURL

class ImageURL(TypedDict):
    url: str                                          # https:// 或 data:image/...;base64,...
    detail: NotRequired[Literal["auto", "low", "high"]]

class AudioContentPart(TypedDict):
    """音频内容块（Phase 4 实现）。"""
    type: Literal["input_audio"]
    input_audio: AudioData

class AudioData(TypedDict):
    data: str                                         # base64 编码
    format: Literal["mp3", "wav", "ogg", "flac"]

# ContentPart 联合类型 — 鉴别器为 type 字段
ContentPart = Union[TextContentPart, ImageContentPart, AudioContentPart]

# content 字段的最终类型：字符串（向后兼容）或内容块列表（多模态）
MessageContent = Union[str, list[ContentPart]]


# ── 消息数据模型 ────────────────────────────────────────────────────────────

class Message(BaseModel):
    """对话中的单条消息。
    
    content 支持两种格式：
    - str：纯文本，Phase 1 唯一使用形式
    - list[ContentPart]：多模态内容块列表（Phase 4 启用）
    """
    role: Literal["system", "user", "assistant", "tool"]
    content: MessageContent
    tool_call_id: str | None = None    # role == "tool" 时使用
    tool_calls: list[ToolCall] | None = None  # role == "assistant" 时可能存在


# ── 工具调用数据模型 ─────────────────────────────────────────────────────────

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict                    # Pydantic 验证后的参数字典


class ToolResult(BaseModel):
    tool_call_id: str
    success: bool
    content: MessageContent            # 工具结果也预留多模态扩展（Phase 4）
    error: str | None = None
```

### 3.3 Phase 1 LLMClient 接口签名

```python
class LLMClient:
    def chat(
        self,
        messages: list[Message],
        tools: list[dict] | None = None,
        stream: bool = False,
    ) -> LLMResponse:
        # Phase 1：断言所有 message.content 均为 str，遇到 list 则抛出 NotImplementedError
        for msg in messages:
            if isinstance(msg.content, list):
                raise NotImplementedError(
                    "Multimodal content parts are not supported in Phase 1. "
                    "Provide content as a plain string."
                )
        # 正常发送纯文本请求...
```

> **设计意图**：Phase 4 只需删除这个 `NotImplementedError` 并实现 `list[ContentPart]` 的序列化逻辑，无需修改调用方代码。

### 3.4 Phase 4 扩展路径

Phase 4 在 `LLMClient.chat()` 中扩展 content 序列化：

```python
def _serialize_content(self, content: MessageContent) -> str | list[dict]:
    if isinstance(content, str):
        return content
    # Phase 4：将 ContentPart 列表转为 OpenAI API 格式
    return [
        {"type": part["type"], **part}
        for part in content
    ]
```

工具返回多模态结果时（Phase 4），`ToolResult.content` 自动支持 `list[ContentPart]`，无需修改工具接口。

---

## 四、Phase 1 需要在 spec.md 中补充的内容

基于本分析，spec.md 的以下位置需要更新：

1. **Key Entities — 对话历史**：补充 content 字段类型为 `Union[str, list[ContentPart]]`
2. **Key Entities — 工具调用结果**：工具返回值同样预留 `MessageContent` 类型
3. **Functional Requirements**：新增 FR-020，要求 Phase 1 的消息 schema 使用 Union 类型

---

## 五、方案选型决策

**采用 LangChain 的 TypedDict + Literal 鉴别器模式**，原因：

| 评估维度 | LangChain 方案 | openai-agents 方案 | ADK 方案 |
|---------|--------------|------------------|---------|
| 类型安全 | ✅ TypedDict + Literal | ❌ 原始 dict | ✅ 数据类 |
| 运行时开销 | 零（TypedDict 不创建对象）| 零 | 低（类实例化）|
| IDE 自动补全 | ✅ 完整 | ❌ 无 | ✅ 完整 |
| 与 OpenAI API 格式对齐 | ✅ 直接对应 | ✅ | ⚠️ 需转换 |
| 向后兼容性 | ✅ | ✅ | ⚠️ 绑定 Google 生态 |
| Phase 1 实现成本 | 极低（纯类型定义）| 极低 | 低 |

> TypedDict 是运行时零成本的纯类型提示结构，非常适合 Phase 1 "只预留类型不实现"的设计目标。

---

## 六、参考文件索引

| 用途 | 文件路径 | 关键行号 |
|------|---------|---------|
| LangChain 消息 content 字段定义 | `reference_projects/langchain/libs/core/langchain_core/messages/base.py` | L103 |
| LangChain TextContentBlock | `reference_projects/langchain/libs/core/langchain_core/messages/content.py` | L207-245 |
| LangChain ImageContentBlock | `reference_projects/langchain/libs/core/langchain_core/messages/content.py` | L498-547 |
| LangChain AudioContentBlock | `reference_projects/langchain/libs/core/langchain_core/messages/content.py` | L600-649 |
| openai-agents 图像转换 | `reference_projects/openai-agents-python/src/agents/models/chatcmpl_converter.py` | L347-363 |
| openai-agents 音频转换 | `reference_projects/openai-agents-python/src/agents/models/chatcmpl_converter.py` | L416-441 |
| ADK 多模态工具结果插件 | `reference_projects/adk-python/src/google/adk/plugins/multimodal_tool_results_plugin.py` | L48-90 |
| hermes-agent 图像工具链 | `reference_projects/hermes-agent/tools/vision_tools.py` | L30-200 |
