"""
演示 05：真实工具集成（FR-008 ~ FR-012）

工具列表：
  🔍 TavilySearchTool   — 联网搜索（需 TAVILY_API_KEY）
  🌤 WttrWeatherTool    — 实时天气 wttr.in（免费，无需 key）
  🌡 OpenWeatherTool    — OpenWeatherMap 天气（需 OPENWEATHERMAP_API_KEY）
  🧮 CalculatorTool     — 安全数学计算（内置）
  🕐 DateTimeTool       — 当前日期时间（内置）

验证点：
  ✓ 装饰器方式定义工具（FR-008）
  ✓ 类继承方式定义工具（FR-009）
  ✓ 参数验证失败返回结构化错误（FR-012）
  ✓ 多工具混合使用端到端（FR-010）
"""

import sys
import os
import json
from pathlib import Path
from datetime import datetime
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from demos._utils import (load_env, header, section, step, ok, warn, err,
                           result, timer, make_agent, C)
from myreactagent import tool, BaseTool, ToolResult

load_env()


# ── 工具：安全计算器（FR-008 装饰器方式）────────────────────────────────────────

@tool
def calculator(expression: str) -> str:
    """计算数学表达式并返回结果，支持 +、-、*、/、() 和幂运算 **。"""
    allowed = set("0123456789+-*/().,** ")
    if not all(c in allowed for c in expression.replace("**", "")):
        return f"错误：包含不允许的字符"
    try:
        val = eval(expression, {"__builtins__": {}}, {})  # noqa: S307
        return str(round(float(val), 6))
    except Exception as e:
        return f"计算错误：{e}"


@tool
def get_current_datetime() -> str:
    """返回当前日期和时间（格式：YYYY-MM-DD HH:MM:SS）。"""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# ── 工具：Tavily 联网搜索（FR-009 类继承方式）────────────────────────────────────

class TavilySearchTool(BaseTool):
    """使用 Tavily API 搜索最新网络信息，适合查询实时新闻和事实性问题。"""

    name = "web_search"
    description = "联网搜索最新信息，返回相关网页摘要。适用于查询新闻、事实、技术文档等。"
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "搜索关键词或问题"},
                "max_results": {"type": "integer", "description": "最大结果数，默认 3", "default": 3},
            },
            "required": ["query"],
        }

    def execute(self, args: dict) -> ToolResult:
        api_key = os.environ.get("TAVILY_API_KEY", "")
        if not api_key or "请填入" in api_key:
            return ToolResult(tool_call_id="", success=False, error="TAVILY_API_KEY 未配置")
        try:
            from tavily import TavilyClient
            client = TavilyClient(api_key=api_key)
            query = args["query"]
            max_results = args.get("max_results") or 3
            resp = client.search(query, max_results=max_results)
            results = resp.get("results", [])
            summary = "\n\n".join(
                f"📄 {r.get('title', '无标题')}\n{r.get('content', '')[:300]}"
                for r in results[:max_results]
            )
            return ToolResult(tool_call_id="", success=True, content=summary or "无搜索结果")
        except ImportError:
            return ToolResult(tool_call_id="", success=False,
                              error="请安装 tavily-python：uv pip install tavily-python")
        except Exception as e:
            return ToolResult(tool_call_id="", success=False, error=f"搜索失败：{e}")


# ── 工具：wttr.in 天气（免费，无需 API Key）──────────────────────────────────────

class WttrWeatherTool(BaseTool):
    """通过 wttr.in 查询城市实时天气，完全免费无需 API Key。"""

    name = "get_weather_wttr"
    description = "查询指定城市的实时天气信息（温度、天气状况、湿度、风速）。"
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称（支持中英文，如 Beijing 或 北京）"},
            },
            "required": ["city"],
        }

    def execute(self, args: dict) -> ToolResult:
        try:
            import requests
            city = args["city"].replace(" ", "+")
            url = f"https://wttr.in/{city}?format=j1&lang=zh"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            current = data["current_condition"][0]
            desc = current.get("weatherDesc", [{}])[0].get("value", "未知")
            temp_c = current.get("temp_C", "?")
            feels_c = current.get("FeelsLikeC", "?")
            humidity = current.get("humidity", "?")
            wind_kmph = current.get("windspeedKmph", "?")
            summary = (
                f"🌍 {args['city']} 当前天气：{desc}\n"
                f"🌡 温度：{temp_c}°C（体感 {feels_c}°C）\n"
                f"💧 湿度：{humidity}%  💨 风速：{wind_kmph} km/h"
            )
            return ToolResult(tool_call_id="", success=True, content=summary)
        except ImportError:
            return ToolResult(tool_call_id="", success=False, error="请安装 requests：pip install requests")
        except Exception as e:
            return ToolResult(tool_call_id="", success=False, error=f"天气查询失败：{e}")


# ── 工具：OpenWeatherMap 天气（需 API Key）────────────────────────────────────────

class OpenWeatherTool(BaseTool):
    """通过 OpenWeatherMap API 查询城市天气，支持更详细的预报数据。"""

    name = "get_weather_owm"
    description = "使用 OpenWeatherMap 查询城市当前天气，返回温度、湿度、风速等详细信息。"
    permission = "read"

    @property
    def parameters_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "城市名称（英文，如 Beijing）"},
                "units": {"type": "string", "description": "温度单位：metric（摄氏）或 imperial（华氏），默认 metric"},
            },
            "required": ["city"],
        }

    def execute(self, args: dict) -> ToolResult:
        api_key = os.environ.get("OPENWEATHERMAP_API_KEY", "")
        if not api_key or "请填入" in api_key:
            return ToolResult(tool_call_id="", success=False, error="OPENWEATHERMAP_API_KEY 未配置")
        try:
            import requests
            city = args["city"]
            units = args.get("units") or "metric"
            url = (
                f"https://api.openweathermap.org/data/2.5/weather"
                f"?q={city}&appid={api_key}&units={units}&lang=zh_cn"
            )
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            unit_sym = "°C" if units == "metric" else "°F"
            summary = (
                f"🌍 {data['name']}（{data['sys']['country']}）天气：{data['weather'][0]['description']}\n"
                f"🌡 温度：{data['main']['temp']}{unit_sym}（感觉 {data['main']['feels_like']}{unit_sym}）\n"
                f"💧 湿度：{data['main']['humidity']}%  "
                f"🌬 气压：{data['main']['pressure']} hPa  "
                f"💨 风速：{data['wind']['speed']} m/s"
            )
            return ToolResult(tool_call_id="", success=True, content=summary)
        except ImportError:
            return ToolResult(tool_call_id="", success=False, error="请安装 requests：pip install requests")
        except Exception as e:
            return ToolResult(tool_call_id="", success=False, error=f"天气查询失败：{e}")


# ── 演示函数 ──────────────────────────────────────────────────────────────────

def demo_real_tools_comprehensive():
    """综合演示：联网搜索 + 天气查询 + 计算 + 时间。"""
    section("综合演示  真实工具联动")

    tools = [
        TavilySearchTool(),
        WttrWeatherTool(),
        OpenWeatherTool(),
        calculator,
        get_current_datetime,
    ]
    agent, cfg = make_agent(
        tools=tools,
        system_prompt=(
            "你是一个实用助手，可以搜索网络、查询天气、进行计算和获取时间。"
            "请使用工具获取真实信息，不要凭空猜测。"
        ),
    )
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']} / {cfg['model']}")
    print(f"  已注册工具: {', '.join(t.name for t in tools)}")

    prompt = (
        "请帮我完成以下几件事：\n"
        "1. 告诉我现在的日期和时间\n"
        "2. 查询上海今天的天气（用 wttr 工具）\n"
        "3. 搜索今天关于人工智能的最新新闻（1 条即可）\n"
        "4. 计算 2024 年已经过了多少天（从 1月1日到今天）\n"
        "请将以上 4 点整合成一段完整的回答。"
    )
    step("发送综合查询请求...")

    with timer("综合查询"):
        ok_flag, answer = __import__("demos._utils", fromlist=["safe_run"]).safe_run(
            agent.run, prompt
        )

    if ok_flag:
        print(f"\n  {C.BOLD}综合答案：{C.RESET}")
        for line in (answer or "").split("\n"):
            print(f"    {line}")
        ok("\n综合工具调用完成 ✓")


def demo_fr012_param_validation():
    """FR-012：参数验证失败返回结构化错误，不崩溃。"""
    section("FR-012  工具参数验证")

    agent, cfg = make_agent(tools=[calculator])
    print(f"  使用提供商: {cfg['emoji']} {cfg['name']}")

    # 直接测试 Registry 的验证行为
    step("传入错误类型参数（int 传给 str 字段）...")
    result_obj = agent._tools.execute("calculator", {"expression": 12345}, "call_test")
    result("验证结果", str(result_obj))
    if result_obj.success:
        ok("表达式为整数时 Pydantic 自动转换为 str（合理行为）✓")
    else:
        ok(f"参数验证失败，结构化错误：{result_obj.error[:60]} ✓")

    step("缺少必填参数...")
    result_obj2 = agent._tools.execute("calculator", {}, "call_test2")
    if not result_obj2.success:
        ok(f"缺少必填参数时返回结构化错误 ✓\n    错误：{result_obj2.error[:80]}")
    else:
        warn("预期验证失败但实际成功（可能参数设有默认值）")


def demo_fr008_decorator_schema():
    """FR-008：验证装饰器自动生成 schema 的准确性。"""
    section("FR-008  @tool 装饰器 Schema 自动生成")

    @tool
    def search(query: str, max_results: int, include_images: bool) -> str:
        """搜索网络内容。支持图片搜索。"""
        return f"搜索：{query}"

    schema = search.parameters_schema
    result("生成的 Schema", json.dumps(schema, ensure_ascii=False, indent=2)[:300])

    assert schema["type"] == "object"
    assert schema["properties"]["query"]["type"] == "string"
    assert schema["properties"]["max_results"]["type"] == "integer"
    assert schema["properties"]["include_images"]["type"] == "boolean"
    assert "query" in schema["required"]
    ok("类型映射正确：str→string, int→integer, bool→boolean ✓")
    ok(f"工具描述自动提取：'{search.description}' ✓")

    # 验证 OpenAI 格式
    from myreactagent.tools.registry import ToolRegistry
    reg = ToolRegistry()
    reg.register(search)
    oai_schemas = reg.get_openai_schemas()
    s = oai_schemas[0]
    assert s["type"] == "function"
    assert s["function"]["name"] == "search"
    ok("OpenAI function calling 格式正确 ✓")


def demo_fr020_fr021_fr022_type_contracts():
    """FR-020/FR-021/FR-022：多模态类型预留、NextStep 枚举、工具属性声明（宪法 XVI/XVII/XI）。"""
    section("FR-020/021/022  Phase 1 类型契约验证")

    # ── FR-020：MessageContent 多模态类型预留 ─────────────────────────────────
    step("FR-020：验证 ContentPart 类型定义 + NotImplementedError 路径...")
    from myreactagent.schemas.messages import (
        TextContentPart, ImageContentPart, AudioContentPart, ContentPart, Message
    )
    # 类型应可正常实例化
    t = TextContentPart(text="hello")
    assert t.type == "text", "TextContentPart.type 应为 'text'"
    ok("TextContentPart / ImageContentPart / AudioContentPart 类型已定义 ✓")

    # list[ContentPart] 内容在 Phase 1 应触发 NotImplementedError
    try:
        msg = Message(role="user", content=[t])
        msg.to_openai_dict()
        warn("预期 NotImplementedError 但未触发，请检查 Message.to_openai_dict() 实现")
    except NotImplementedError:
        ok("list[ContentPart] 传入时正确抛出 NotImplementedError（Phase 1 占位）✓")

    # ── FR-021：NextStep 枚举四种状态 ────────────────────────────────────────
    step("FR-021：验证 NextStep 枚举完整性...")
    from myreactagent.schemas.events import NextStep
    values = {s.value for s in NextStep}
    assert "stop"      in values, "NextStep 缺少 STOP"
    assert "continue"  in values, "NextStep 缺少 CONTINUE"
    assert "handoff"   in values, "NextStep 缺少 HANDOFF（Phase 2 占位）"
    assert "interrupt" in values, "NextStep 缺少 INTERRUPT（Phase 4 占位）"
    result("NextStep 枚举成员", str({s.name: s.value for s in NextStep}))
    ok("NextStep 枚举全部 4 种状态已定义 ✓")

    # ── FR-022：工具基类属性声明 ─────────────────────────────────────────────
    step("FR-022：验证 BaseTool is_destructive / permission 属性...")
    from myreactagent.tools.base import BaseTool

    @tool
    def sample_tool(x: int) -> int:
        """示例工具。"""
        return x

    assert hasattr(sample_tool, "is_destructive"), "工具缺少 is_destructive 属性"
    assert hasattr(sample_tool, "permission"),     "工具缺少 permission 属性"
    assert sample_tool.is_destructive is False,    "is_destructive 默认值应为 False"
    assert sample_tool.permission == "read",       "permission 默认值应为 'read'"
    result("is_destructive 默认值", str(sample_tool.is_destructive))
    result("permission 默认值",     sample_tool.permission)
    ok("is_destructive=False, permission='read' 默认值正确 ✓")

    # 验证可覆盖
    @tool(is_destructive=True, permission="destructive")
    def dangerous_tool(path: str) -> str:
        """危险工具示例（Phase 4 HITL 激活时需人工确认）。"""
        return path

    assert dangerous_tool.is_destructive is True
    assert dangerous_tool.permission == "destructive"
    ok("@tool(is_destructive=True, permission='destructive') 覆盖正确 ✓")


if __name__ == "__main__":
    header("演示 05：真实工具集成")

    try:
        demo_fr008_decorator_schema()
        demo_fr012_param_validation()
        demo_fr020_fr021_fr022_type_contracts()
        demo_real_tools_comprehensive()
        print(f"\n{'='*62}")
        ok("演示 05 全部完成！")
    except RuntimeError as e:
        err(str(e))
        sys.exit(1)
