"""演示脚本共用工具：环境加载、彩色输出、多模型提供商配置。"""

from __future__ import annotations

import contextlib
import os
import sys
import time
from pathlib import Path


# ── ANSI 彩色输出 ─────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    BLUE   = "\033[94m"
    CYAN   = "\033[96m"
    RED    = "\033[91m"
    GRAY   = "\033[90m"
    PURPLE = "\033[95m"


def header(title: str) -> None:
    print(f"\n{C.BOLD}{C.BLUE}{'═'*62}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}  {title}{C.RESET}")
    print(f"{C.BOLD}{C.BLUE}{'═'*62}{C.RESET}")


def section(title: str) -> None:
    print(f"\n{C.BOLD}{C.CYAN}── {title} {'─'*(56-len(title))}{C.RESET}")


def step(msg: str) -> None:
    print(f"  {C.CYAN}▶{C.RESET} {msg}")


def ok(msg: str) -> None:
    print(f"  {C.GREEN}✅{C.RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {C.YELLOW}⚠️ {C.RESET} {msg}")


def err(msg: str) -> None:
    print(f"  {C.RED}❌{C.RESET} {msg}")


def result(label: str, value: str) -> None:
    short = value[:120] + "…" if len(value) > 120 else value
    print(f"  {C.BOLD}{label}:{C.RESET} {short}")


def divider() -> None:
    print(f"  {C.GRAY}{'─'*58}{C.RESET}")


# ── .env 加载 ─────────────────────────────────────────────────────────────────

def load_env() -> None:
    """从 demos/.env 加载环境变量（已有值的不覆盖）。"""
    # 依次尝试 demos/.env 和项目根 .env
    candidates = [
        Path(__file__).parent / ".env",
        Path(__file__).parent.parent / ".env",
    ]
    for env_file in candidates:
        if env_file.exists():
            with open(env_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, val = line.partition("=")
                        key = key.strip()
                        val = val.strip().strip('"').strip("'")
                        # 跳过占位符
                        if key and val and "请填入" not in val and val not in ("", "..."):
                            os.environ.setdefault(key, val)
            break


# ── 模型提供商注册表 ───────────────────────────────────────────────────────────

_PROVIDERS: dict[str, dict] = {
    "openai": {
        "name": "OpenAI",
        "emoji": "🟢",
        "api_key_env": "OPENAI_API_KEY",
        "base_url_env": "OPENAI_BASE_URL",
        "model_env": "OPENAI_MODEL",
        "default_model": "gpt-4o-mini",
        "default_base_url": None,
        "tool_support": True,
    },
    "deepseek": {
        "name": "DeepSeek",
        "emoji": "🔵",
        "api_key_env": "DEEPSEEK_API_KEY",
        "base_url_env": "DEEPSEEK_BASE_URL",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
        "default_base_url": "https://api.deepseek.com",
        "tool_support": True,
    },
    "dashscope": {
        "name": "DashScope (Qwen)",
        "emoji": "🟠",
        "api_key_env": "DASHSCOPE_API_KEY",
        "base_url_env": "DASHSCOPE_BASE_URL",
        "model_env": "DASHSCOPE_MODEL",
        "default_model": "qwen-plus",
        "default_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "tool_support": True,
    },
    "gemini": {
        "name": "Google Gemini",
        "emoji": "🔴",
        "api_key_env": "GEMINI_API_KEY",
        "base_url_env": "GEMINI_BASE_URL",
        "model_env": "GEMINI_MODEL",
        "default_model": "gemini-2.0-flash",
        "default_base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "tool_support": True,
    },
    "anthropic": {
        "name": "Anthropic Claude",
        "emoji": "🟣",
        "api_key_env": "ANTHROPIC_API_KEY",
        "base_url_env": None,
        "model_env": "ANTHROPIC_MODEL",
        "default_model": "claude-3-5-haiku-20241022",
        "default_base_url": None,
        "tool_support": True,   # 通过原生 SDK 适配
        "native_sdk": True,     # 使用 _anthropic_adapter 而非 openai SDK
    },
}

# 默认探测顺序
_PRIORITY = ["deepseek", "openai", "dashscope", "gemini", "anthropic"]


def get_provider_config(provider_id: str) -> dict | None:
    """获取指定提供商配置，API Key 未设置时返回 None。"""
    p = _PROVIDERS.get(provider_id)
    if not p:
        return None
    api_key = os.environ.get(p["api_key_env"], "")
    if not api_key or "请填入" in api_key:
        return None

    base_url_env = p.get("base_url_env")
    base_url = (
        (os.environ.get(base_url_env) if base_url_env else None)
        or p["default_base_url"]
    )
    model = (
        (os.environ.get(p["model_env"]) if p.get("model_env") else None)
        or p["default_model"]
    )
    return {
        "id": provider_id,
        "name": p["name"],
        "emoji": p["emoji"],
        "api_key": api_key,
        "base_url": base_url,
        "model": model,
        "tool_support": p.get("tool_support", True),
        "native_sdk": p.get("native_sdk", False),
    }


def list_available_providers() -> list[dict]:
    """返回所有已配置 API Key 的提供商列表。"""
    return [cfg for pid in _PRIORITY if (cfg := get_provider_config(pid))]


def get_default_provider() -> dict | None:
    """按优先级返回第一个可用提供商（可用 DEMO_DEFAULT_PROVIDER 覆盖）。"""
    override = os.environ.get("DEMO_DEFAULT_PROVIDER")
    if override:
        return get_provider_config(override)
    providers = list_available_providers()
    return providers[0] if providers else None


# ── 提供商上下文管理器 ────────────────────────────────────────────────────────

@contextlib.contextmanager
def use_provider(cfg: dict):
    """临时设置 OPENAI_* 环境变量以切换 LLMClient 的后端。"""
    saved = {
        "OPENAI_API_KEY": os.environ.get("OPENAI_API_KEY"),
        "OPENAI_BASE_URL": os.environ.get("OPENAI_BASE_URL"),
        "OPENAI_MODEL": os.environ.get("OPENAI_MODEL"),
    }
    try:
        os.environ["OPENAI_API_KEY"] = cfg["api_key"]
        if cfg["base_url"]:
            os.environ["OPENAI_BASE_URL"] = cfg["base_url"]
        elif "OPENAI_BASE_URL" in os.environ:
            del os.environ["OPENAI_BASE_URL"]
        os.environ["OPENAI_MODEL"] = cfg["model"]
        yield cfg
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
            elif k in os.environ:
                del os.environ[k]


# ── ReactAgent 工厂 ───────────────────────────────────────────────────────────

def make_agent(provider_cfg: dict | None = None, **kwargs):
    """使用指定提供商配置创建 ReactAgent，返回 (agent, provider_cfg) 元组。"""
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from myreactagent import ReactAgent

    cfg = provider_cfg or get_default_provider()
    if cfg is None:
        raise RuntimeError("未找到任何有效的 API Key，请检查 demos/.env")

    if cfg.get("native_sdk"):
        # Anthropic 使用原生 SDK 适配器
        from demos._anthropic_adapter import AnthropicReactAgent
        agent = AnthropicReactAgent(
            api_key=cfg["api_key"],
            model=cfg["model"],
            **kwargs,
        )
    else:
        agent = ReactAgent(
            model=cfg["model"],
            base_url=cfg["base_url"],
            api_key=cfg["api_key"],
            **kwargs,
        )

    return agent, cfg


# ── 计时装饰器 ────────────────────────────────────────────────────────────────

@contextlib.contextmanager
def timer(label: str = ""):
    start = time.perf_counter()
    yield
    elapsed = time.perf_counter() - start
    tag = f" [{label}]" if label else ""
    print(f"  {C.GRAY}⏱ 耗时{tag}: {elapsed:.2f}s{C.RESET}")


# ── 安全 API 调用（带错误展示）────────────────────────────────────────────────

def safe_run(fn, *args, **kwargs):
    """执行函数，捕获异常并打印，返回 (成功, 结果) 元组。"""
    try:
        return True, fn(*args, **kwargs)
    except Exception as e:
        err(f"{type(e).__name__}: {e}")
        return False, None
