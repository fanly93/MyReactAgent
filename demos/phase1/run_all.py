"""
Phase 1 全量演示运行器

一键运行所有 Phase 1 演示，汇总通过/跳过/失败结果。

用法：
  python demos/phase1/run_all.py             # 运行全部
  python demos/phase1/run_all.py 01 03       # 只运行指定演示
  python demos/phase1/run_all.py --skip 06   # 跳过指定演示
"""

import sys
import time
import subprocess
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
PHASE1_DIR = Path(__file__).parent

DEMOS = [
    ("01", "基础 ReAct 循环", "01_basic_react_loop.py"),
    ("02", "多轮对话记忆",     "02_multi_turn_memory.py"),
    ("03", "实时流式输出",     "03_streaming.py"),
    ("04", "执行过程可观测性", "04_callbacks.py"),
    ("05", "真实工具集成",     "05_tools_advanced.py"),
    ("06", "多模型提供商对比", "06_multi_provider.py"),
]

# ── ANSI 颜色 ──────────────────────────────────────────────────────────────────

class C:
    RESET  = "\033[0m"
    BOLD   = "\033[1m"
    RED    = "\033[91m"
    GREEN  = "\033[92m"
    YELLOW = "\033[93m"
    CYAN   = "\033[96m"
    GRAY   = "\033[90m"


def banner(text: str):
    line = "=" * 62
    print(f"\n{C.BOLD}{C.CYAN}{line}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  {text}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{line}{C.RESET}\n")


def run_demo(num: str, title: str, filename: str, timeout: int = 300) -> str:
    """运行单个演示文件，返回 'pass' / 'fail' / 'timeout'。"""
    script = PHASE1_DIR / filename
    print(f"\n{C.BOLD}{'─'*62}{C.RESET}")
    print(f"{C.BOLD}▶  演示 {num}：{title}{C.RESET}")
    print(f"{C.GRAY}   {script.relative_to(ROOT)}{C.RESET}\n")

    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            timeout=timeout,
            check=False,
        )
        elapsed = time.perf_counter() - t0
        if result.returncode == 0:
            print(f"\n{C.GREEN}  ✓ 演示 {num} 通过  ({elapsed:.1f}s){C.RESET}")
            return "pass"
        else:
            print(f"\n{C.RED}  ✗ 演示 {num} 失败  (exit={result.returncode}, {elapsed:.1f}s){C.RESET}")
            return "fail"
    except subprocess.TimeoutExpired:
        elapsed = time.perf_counter() - t0
        print(f"\n{C.YELLOW}  ⏱ 演示 {num} 超时  ({elapsed:.1f}s){C.RESET}")
        return "timeout"
    except Exception as e:
        print(f"\n{C.RED}  ✗ 运行出错：{e}{C.RESET}")
        return "fail"


def parse_args():
    """解析命令行参数，返回 (include_nums, skip_nums)。"""
    args = sys.argv[1:]
    include = []
    skip = []
    skip_mode = False
    for a in args:
        if a == "--skip":
            skip_mode = True
        elif skip_mode:
            skip.append(a.zfill(2))
            skip_mode = False
        else:
            include.append(a.zfill(2))
    return include, skip


def main():
    banner("MyReactAgent — Phase 1 全量演示")

    include, skip = parse_args()

    to_run = [
        d for d in DEMOS
        if (not include or d[0] in include) and d[0] not in skip
    ]

    if not to_run:
        print(f"{C.YELLOW}  没有匹配的演示可运行。{C.RESET}")
        sys.exit(0)

    print(f"  将运行 {len(to_run)} 个演示：{', '.join(d[0] for d in to_run)}")
    if skip:
        print(f"  已跳过：{', '.join(skip)}")

    results = {}
    total_t0 = time.perf_counter()

    for num, title, filename in to_run:
        results[num] = run_demo(num, title, filename)

    total_elapsed = time.perf_counter() - total_t0

    # ── 汇总 ──────────────────────────────────────────────────────────────────
    banner("演示结果汇总")
    passed  = [n for n, s in results.items() if s == "pass"]
    failed  = [n for n, s in results.items() if s == "fail"]
    timeout = [n for n, s in results.items() if s == "timeout"]

    for num, title, _ in DEMOS:
        if num not in results:
            continue
        status = results[num]
        if status == "pass":
            icon = f"{C.GREEN}✓ 通过{C.RESET}"
        elif status == "timeout":
            icon = f"{C.YELLOW}⏱ 超时{C.RESET}"
        else:
            icon = f"{C.RED}✗ 失败{C.RESET}"
        print(f"  演示 {num} — {title:<12}  {icon}")

    print(f"\n  总耗时：{total_elapsed:.1f}s")
    print(f"  通过：{C.GREEN}{len(passed)}{C.RESET}  "
          f"失败：{C.RED}{len(failed)}{C.RESET}  "
          f"超时：{C.YELLOW}{len(timeout)}{C.RESET}  "
          f"共 {len(results)} 个")

    if not failed and not timeout:
        print(f"\n{C.GREEN}{C.BOLD}  🎉 Phase 1 全部演示通过！{C.RESET}")
        sys.exit(0)
    else:
        print(f"\n{C.YELLOW}  部分演示未通过，请检查上方输出。{C.RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
