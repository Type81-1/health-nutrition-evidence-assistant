"""一键验收脚本 —— 项目交付必备。

功能：
  1. 基础功能回归（快测 10 题）  →  < 2 min
  2. 完整 128 题问卷评测          →  ~25 min
  3. 失败案例突出展示
  4. 结构化报告输出（JSON + Markdown）
  5. 与上次结果对比（如存在）

使用方法:
    python scripts/evaluate.py              # 完整评测
    python scripts/evaluate.py --quick      # 快测（10 题抽查）
    python scripts/evaluate.py --json       # 仅输出 JSON（供 CI 使用）

输出:
    data/eval_result.json    — 结构化评测结果
    evaluation_report.md     — 可读报告（被 --quick / 完整评测覆盖）
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


# ═══════════════════════════════════════════════════════════════
# 配置
# ═══════════════════════════════════════════════════════════════

RESULT_FILE = ROOT / "data" / "eval_result.json"

EVAL_SCRIPTS = {
    "basic": {
        "script": "run_evaluation.py",
        "description": "RAG vs 裸LLM 对比评测",
        "quick_only": False,
    },
    "survey": {
        "script": "run_survey_eval.py",
        "description": "128 题综合问卷评测",
        "quick_only": False,
    },
}


# ═══════════════════════════════════════════════════════════════
# 辅助
# ═══════════════════════════════════════════════════════════════

def run_script(script_name: str, args: list[str] | None = None) -> dict:
    """运行评测子脚本并返回结果摘要。"""
    args = args or []
    script_path = ROOT / "scripts" / script_name
    if not script_path.exists():
        return {"success": False, "error": f"脚本不存在: {script_path}"}

    t0 = time.perf_counter()
    try:
        result = subprocess.run(
            [sys.executable, str(script_path)] + args,
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=1800,  # 30 分钟上限
        )
        elapsed = time.perf_counter() - t0
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout[-3000:],  # 保留末尾输出
            "stderr": result.stderr[-1000:],
            "elapsed_s": round(elapsed, 1),
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "脚本执行超时（30 min）", "elapsed_s": 1800}
    except Exception as e:
        return {"success": False, "error": str(e), "elapsed_s": time.perf_counter() - t0}


def load_previous_result() -> dict | None:
    """加载上次评测结果用于对比。"""
    if RESULT_FILE.exists():
        try:
            return json.loads(RESULT_FILE.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return None


def extract_score_from_stdout(stdout: str) -> dict:
    """从脚本 stdout 中提取评分信息。"""
    import re

    info: dict = {"total_score": None, "max_score": None, "ratio": None}

    # 匹配 "总计 | ... | N | M | X%" 格式
    total_match = re.search(
        r"总计.*?\|\s*[\d.]+\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)\s*\|\s*([\d.]+)%",
        stdout,
    )
    if total_match:
        info["total_score"] = float(total_match.group(1))
        info["max_score"] = float(total_match.group(2))
        info["ratio"] = float(total_match.group(3))

    # 匹配 "总计" 行（survey 格式）
    survey_match = re.search(
        r"总计.*?\|\s*\d+\s*\|\s*([\d.]+)\s*\|\s*(\d+)\s*\|\s*([\d.]+)%",
        stdout,
    )
    if survey_match:
        info["total_score"] = float(survey_match.group(1))
        info["max_score"] = float(survey_match.group(2))
        info["ratio"] = float(survey_match.group(3))

    # 匹配 RAG 平均分
    rag_match = re.search(r"平均分\s+([\d.]+)", stdout)
    if rag_match:
        info["rag_avg"] = float(rag_match.group(1))

    return info


def compare_with_previous(current: dict, previous: dict | None) -> dict:
    """对比前后两次评测结果。"""
    if previous is None:
        return {"has_previous": False}

    comparison = {"has_previous": True}

    curr_ratio = current.get("ratio")
    prev_ratio = previous.get("ratio")
    if curr_ratio is not None and prev_ratio is not None:
        comparison["ratio_change"] = round(curr_ratio - prev_ratio, 1)
        comparison["degraded"] = curr_ratio < prev_ratio

    curr_score = current.get("total_score")
    prev_score = previous.get("total_score")
    if curr_score is not None and prev_score is not None:
        comparison["score_change"] = round(curr_score - prev_score, 1)

    return comparison


# ═══════════════════════════════════════════════════════════════
# 主流程
# ═══════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(description="食证 · 一键验收脚本")
    parser.add_argument("--quick", action="store_true", help="快测模式（10 题抽查，< 2 min）")
    parser.add_argument("--json", action="store_true", help="仅输出 JSON 结果")
    args = parser.parse_args()

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    results: dict = {
        "timestamp": timestamp,
        "mode": "quick" if args.quick else "full",
        "scripts": {},
        "summary": {},
    }

    if not args.json:
        print("=" * 70)
        print("食证 · 一键验收评测")
        print(f"时间: {timestamp}  |  模式: {results['mode']}")
        print("=" * 70)

    # ── 运行评测脚本 ──
    for key, cfg in EVAL_SCRIPTS.items():
        if args.quick and cfg.get("quick_only") is False and key != "basic":
            continue

        if not args.json:
            print(f"\n▶ {cfg['description']} ({cfg['script']})")

        script_args = ["--quick"] if (args.quick and key == "survey") else []
        outcome = run_script(cfg["script"], script_args)

        score_info = {}
        if outcome.get("stdout"):
            score_info = extract_score_from_stdout(outcome["stdout"])

        results["scripts"][key] = {
            "description": cfg["description"],
            "success": outcome["success"],
            "elapsed_s": outcome.get("elapsed_s", 0),
            "error": outcome.get("error", ""),
            **score_info,
        }

        if not args.json:
            status = "✅" if outcome["success"] else "❌"
            score_str = f" 得分 {score_info.get('total_score', '?')}/{score_info.get('max_score', '?')}" if score_info.get("total_score") else ""
            print(f"  {status} 耗时 {outcome.get('elapsed_s', 0):.0f}s{score_str}")
            if outcome.get("error"):
                print(f"  错误: {outcome['error']}")

    # ── 汇总 ──
    all_ok = all(r["success"] for r in results["scripts"].values())
    total_score = None
    total_max = None

    # 尝试从 survey 结果提取总分
    survey_result = results["scripts"].get("survey", {})
    if survey_result.get("total_score"):
        total_score = survey_result["total_score"]
        total_max = survey_result["max_score"]

    results["summary"] = {
        "all_passed": all_ok,
        "total_score": total_score,
        "total_max": total_max,
        "ratio": survey_result.get("ratio"),
        "total_elapsed_s": round(sum(r.get("elapsed_s", 0) for r in results["scripts"].values()), 1),
    }

    # ── 与上次对比 ──
    previous = load_previous_result()
    comparison = compare_with_previous(results["summary"], previous.get("summary") if previous else None)
    results["comparison"] = comparison

    # ── 保存结果 ──
    RESULT_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESULT_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 终端输出 ──
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return 0 if all_ok else 1

    print("\n" + "=" * 70)
    print("评测汇总")
    print("=" * 70)

    summary = results["summary"]
    status_icon = "✅ 全部通过" if all_ok else "❌ 存在失败"
    print(f"  状态: {status_icon}")
    if total_score is not None:
        print(f"  得分: {total_score}/{total_max} ({summary['ratio']}%)")
    print(f"  总耗时: {summary['total_elapsed_s']:.0f}s")

    if comparison.get("has_previous"):
        if comparison.get("degraded"):
            print(f"  ⚠️  得分退化: {comparison.get('ratio_change', 0):+.1f}%")
        elif comparison.get("ratio_change", 0) > 0:
            print(f"  📈 得分提升: {comparison.get('ratio_change', 0):+.1f}%")
        else:
            print("  ➡️  得分持平")

    # ── 失败案例高亮 ──
    failed = {k: v for k, v in results["scripts"].items() if not v["success"]}
    if failed:
        print(f"\n⚠️  失败脚本 ({len(failed)}):")
        for key, info in failed.items():
            print(f"  - {info['description']}: {info.get('error', '未知错误')}")

    print(f"\n详细结果: {RESULT_FILE}")
    print(f"完成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
