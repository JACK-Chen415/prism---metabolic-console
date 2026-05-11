"""Benchmark Doubao streaming latency without logging prompts or secrets.

Usage examples:
  python scripts/benchmark_doubao_latency.py --runs 3
  python scripts/benchmark_doubao_latency.py --full-matrix --runs 3
  python scripts/benchmark_doubao_latency.py --models "$env:DOUBAO_MODEL,$env:DOUBAO_FAST_MODEL"
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import statistics
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
except Exception:
    pass

from app.core.config import settings  # noqa: E402
from app.services.ai_service import SYSTEM_PROMPT  # noqa: E402


DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
DEFAULT_REGION = "cn-beijing"


@dataclass(frozen=True)
class Scenario:
    name: str
    messages: list[dict[str, str]]

    @property
    def prompt_chars(self) -> int:
        return sum(len(message.get("content") or "") for message in self.messages)

    @property
    def message_count(self) -> int:
        return len(self.messages)


@dataclass(frozen=True)
class BenchmarkCase:
    scenario: Scenario
    model: str
    base_url: str
    region: str
    max_tokens: int
    temperature: float

    @property
    def key(self) -> tuple[str, str, int, float]:
        return (self.scenario.name, self.model, self.max_tokens, self.temperature)


def _current_system_prompt() -> str:
    return SYSTEM_PROMPT.format(
        user_context=(
            "- 慢性病史：高尿酸/痛风（稳定期），需控制嘌呤和酒精。\n"
            "- 推荐摄入目标：热量 1800kcal，钠 <2000mg，嘌呤 <300mg。\n"
            "- 重要提醒：本地 LIMIT/AVOID 规则优先，云端不得放宽。"
        )
    )


def _compact_system_prompt() -> str:
    return (
        "你是健康饮食助手。请用中文给出安全、具体、可执行的饮食建议。"
        "不要做医疗诊断；高风险症状建议就医。"
        "若本地规则命中 LIMIT 或 AVOID，只能解释原因和替代建议，绝不可放宽结论。"
    )


def _compressed_guardrail_prompt() -> str:
    return (
        "你是 PRISM 健康饮食助手，回答需简洁、循证、可执行。\n"
        "安全边界：不诊断疾病；不建议停药或换药；急症提示就医。\n"
        "本地规则优先：若知识库命中 AVOID/LIMIT/过敏/忌口，云端不得改判，只能说明原因、给替代方案。\n"
        "用户档案摘要：高尿酸/痛风稳定期，控制嘌呤、酒精和含糖饮料；每日热量约 1800kcal，钠 <2000mg。\n"
        "本地知识摘要：啤酒 AVOID；沙丁鱼 AVOID；含糖汽水 LIMIT；低脂奶、鸡蛋、蔬菜和白水优先。"
    )


def _long_history_messages() -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    user_line = (
        "我今天记录了米饭、鸡蛋、青菜、少量鸡胸肉，也担心晚餐太晚、总热量偏高和痛风风险。"
        "请记住我想要简单、可执行、不要太油腻的建议。"
        "我平时外卖较多，容易摄入高盐高油菜品，希望建议能兼顾控热量、控钠、控嘌呤、提高饱腹感，"
        "并给出普通食堂或便利店也能做到的替代选择。"
        "我不想要复杂菜谱，更需要能直接照着点餐或搭配的方案，例如主食、蛋白、蔬菜、饮品各选什么。"
        "如果存在风险食物，请明确替代项和理由。"
    )
    assistant_line = (
        "已记录。建议主食定量，搭配足量蔬菜和优质蛋白，控制高嘌呤食物、酒精和含糖饮料，"
        "并注意晚餐七分饱、少油少盐。"
        "如果必须点外卖，优先选择清蒸、白灼、少油炒菜或汤面少汤，避开炸物、浓酱、动物内脏、啤酒、"
        "含糖饮料和高嘌呤海鲜，同时把主食控制在一拳左右。"
        "建议每次只给两到三个选择，并说明为什么这些选择更稳妥，避免建议过长导致执行困难。"
        "回答时优先给可马上执行的搭配。"
    )
    for i in range(1, 13):
        if i % 2:
            messages.append({"role": "user", "content": f"第{i}轮：{user_line}"})
        else:
            messages.append({"role": "assistant", "content": f"第{i}轮回复：{assistant_line}"})
    messages.append({"role": "user", "content": "结合前面的记录，用三句话给我一个今晚饮食安排。"})
    return messages


def build_scenarios() -> dict[str, Scenario]:
    short = Scenario(
        name="short_compact",
        messages=[
            {"role": "system", "content": _compact_system_prompt()},
            {"role": "user", "content": "请用 100 字说明晚餐如何吃得更健康。"},
        ],
    )
    medium = Scenario(
        name="medium_current",
        messages=[
            {"role": "system", "content": _current_system_prompt()},
            {"role": "user", "content": "请用两句话告诉我今天晚饭应该怎么吃更健康。"},
        ],
    )
    compressed = Scenario(
        name="compressed_guardrail",
        messages=[
            {"role": "system", "content": _compressed_guardrail_prompt()},
            {"role": "user", "content": "请用两句话告诉我今天晚饭应该怎么吃更健康。"},
        ],
    )
    long = Scenario(
        name="long_current",
        messages=[{"role": "system", "content": _current_system_prompt()}] + _long_history_messages(),
    )
    return {scenario.name: scenario for scenario in (short, medium, compressed, long)}


def parse_csv_values(raw: str, cast) -> list[Any]:
    values = []
    for item in (raw or "").split(","):
        item = item.strip()
        if item:
            values.append(cast(item))
    return values


def configured_models(raw: str | None) -> list[str]:
    if raw:
        return [model for model in parse_csv_values(raw, str) if model]

    models = [settings.main_doubao_model]
    fast_model = os.getenv("DOUBAO_FAST_MODEL", "").strip()
    if fast_model and fast_model not in models:
        models.append(fast_model)
    return models


def build_cases(args: argparse.Namespace, scenarios: dict[str, Scenario]) -> list[BenchmarkCase]:
    selected_scenarios = parse_csv_values(args.scenarios, str) if args.scenarios else list(scenarios)
    missing = [name for name in selected_scenarios if name not in scenarios]
    if missing:
        raise SystemExit(f"Unknown scenarios: {', '.join(missing)}. Available: {', '.join(scenarios)}")

    max_tokens = parse_csv_values(args.max_tokens, int)
    temperatures = parse_csv_values(args.temperatures, float)
    models = configured_models(args.models)
    base_url = args.base_url or DEFAULT_BASE_URL
    region = args.region or DEFAULT_REGION

    cases: list[BenchmarkCase] = []
    seen: set[tuple[str, str, int, float]] = set()

    def add_case(scenario_name: str, model: str, tokens: int, temperature: float) -> None:
        case = BenchmarkCase(
            scenario=scenarios[scenario_name],
            model=model,
            base_url=base_url,
            region=region,
            max_tokens=tokens,
            temperature=temperature,
        )
        if case.key not in seen:
            seen.add(case.key)
            cases.append(case)

    if args.full_matrix:
        for model in models:
            for scenario_name in selected_scenarios:
                for tokens in max_tokens:
                    for temperature in temperatures:
                        add_case(scenario_name, model, tokens, temperature)
        return cases

    # Core profile: enough to isolate max_tokens, prompt length, and temperature
    # while keeping real API runtime reasonable.
    core_temperature = args.core_temperature
    core_tokens = args.core_max_tokens
    for model in models:
        for tokens in max_tokens:
            add_case("medium_current", model, tokens, core_temperature)
        for scenario_name in ("short_compact", "compressed_guardrail", "long_current"):
            add_case(scenario_name, model, core_tokens, core_temperature)
        for temperature in temperatures:
            add_case("medium_current", model, core_tokens, temperature)
    return cases


def percentile(values: list[float], ratio: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * ratio)))
    return ordered[index]


def new_client(*, api_key: str, base_url: str, region: str, timeout_seconds: float, connect_timeout_seconds: float, max_retries: int):
    import httpx
    from volcenginesdkarkruntime import Ark

    return Ark(
        api_key=api_key,
        base_url=base_url,
        region=region,
        timeout=httpx.Timeout(timeout=timeout_seconds, connect=connect_timeout_seconds),
        max_retries=max_retries,
    )


def run_once(client: Any, case: BenchmarkCase) -> dict[str, Any]:
    created_at = datetime.now(timezone.utc).isoformat()
    request_id = uuid.uuid4().hex[:12]
    started = time.perf_counter()
    first_chunk_ms: float | None = None
    response_chars = 0
    error_type = None
    error_message = None
    success = False

    try:
        stream = client.chat.completions.create(
            model=case.model,
            messages=case.scenario.messages,
            temperature=case.temperature,
            max_tokens=case.max_tokens,
            stream=True,
        )
        while True:
            try:
                chunk = next(stream)
            except StopIteration:
                break
            content = ""
            if chunk.choices and chunk.choices[0].delta.content:
                content = chunk.choices[0].delta.content
            if not content:
                continue
            if first_chunk_ms is None:
                first_chunk_ms = round((time.perf_counter() - started) * 1000, 2)
            response_chars += len(content)
        success = True
    except Exception as exc:
        error_type = exc.__class__.__name__
        error_message = str(exc).replace(os.getenv("ARK_API_KEY", "") or "__NO_KEY__", "[redacted]")[:240]

    total_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "request_id": request_id,
        "scenario": case.scenario.name,
        "model": case.model,
        "base_url": case.base_url,
        "region": case.region,
        "max_tokens": case.max_tokens,
        "temperature": case.temperature,
        "prompt_chars": case.scenario.prompt_chars,
        "message_count": case.scenario.message_count,
        "first_chunk_ms": first_chunk_ms,
        "total_ms": total_ms,
        "response_chars": response_chars,
        "success": success,
        "error_type": error_type,
        "error_message": error_message,
        "created_at": created_at,
    }


def summarize(results: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    groups: dict[tuple[str, str, int, float], list[dict[str, Any]]] = {}
    for result in results:
        key = (result["scenario"], result["model"], result["max_tokens"], result["temperature"])
        groups.setdefault(key, []).append(result)

    summary_rows = []
    for (scenario, model, max_tokens, temperature), rows in sorted(groups.items()):
        successful = [row for row in rows if row["success"] and row["first_chunk_ms"] is not None]
        first_values = [float(row["first_chunk_ms"]) for row in successful]
        total_values = [float(row["total_ms"]) for row in successful]
        response_values = [int(row["response_chars"]) for row in successful]
        prompt_chars = rows[0]["prompt_chars"]
        summary_rows.append(
            {
                "scenario": scenario,
                "model": model,
                "max_tokens": max_tokens,
                "temperature": temperature,
                "prompt_chars": prompt_chars,
                "runs": len(rows),
                "successes": len(successful),
                "first_chunk_avg_ms": round(statistics.mean(first_values), 2) if first_values else None,
                "first_chunk_min_ms": round(min(first_values), 2) if first_values else None,
                "first_chunk_max_ms": round(max(first_values), 2) if first_values else None,
                "first_chunk_p50_ms": round(percentile(first_values, 0.50), 2) if first_values else None,
                "first_chunk_p90_ms": round(percentile(first_values, 0.90), 2) if first_values else None,
                "total_avg_ms": round(statistics.mean(total_values), 2) if total_values else None,
                "response_chars_avg": round(statistics.mean(response_values), 2) if response_values else None,
            }
        )
    return summary_rows


def print_markdown_table(rows: list[dict[str, Any]]) -> None:
    headers = [
        "scenario",
        "model",
        "max_tokens",
        "temperature",
        "prompt_chars",
        "runs",
        "successes",
        "first_chunk_avg_ms",
        "first_chunk_min_ms",
        "first_chunk_max_ms",
        "first_chunk_p50_ms",
        "first_chunk_p90_ms",
        "total_avg_ms",
        "response_chars_avg",
    ]
    print("| " + " | ".join(headers) + " |")
    print("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        print("| " + " | ".join(str(row.get(header, "")) for header in headers) + " |")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(description="Benchmark Doubao streaming first-chunk latency.")
    parser.add_argument("--runs", type=int, default=3, help="Runs per case.")
    parser.add_argument("--models", default="", help="Comma-separated model ids. Defaults to DOUBAO_MODEL plus optional DOUBAO_FAST_MODEL.")
    parser.add_argument("--base-url", default=os.getenv("ARK_BASE_URL", DEFAULT_BASE_URL), help="Ark base URL. No API key is logged.")
    parser.add_argument("--region", default=os.getenv("ARK_REGION", DEFAULT_REGION))
    parser.add_argument("--max-tokens", default="600,800,1000")
    parser.add_argument("--temperatures", default="0.2,0.5,0.7")
    parser.add_argument("--core-max-tokens", type=int, default=800)
    parser.add_argument("--core-temperature", type=float, default=0.5)
    parser.add_argument("--scenarios", default="", help="Comma-separated scenarios. Defaults to all known scenarios.")
    parser.add_argument("--full-matrix", action="store_true", help="Run every scenario x max_tokens x temperature combination.")
    parser.add_argument("--timeout-seconds", type=float, default=settings.doubao_timeout_seconds)
    parser.add_argument("--connect-timeout-seconds", type=float, default=settings.doubao_connect_timeout_seconds)
    parser.add_argument("--max-retries", type=int, default=settings.doubao_max_retries)
    parser.add_argument("--output-dir", default=str(ROOT / "perf_results"))
    parser.add_argument("--csv", action="store_true", help="Also write a CSV summary.")
    args = parser.parse_args()

    if args.runs < 1:
        raise SystemExit("--runs must be >= 1")
    if not settings.ark_api_key:
        raise SystemExit("ARK_API_KEY is not configured.")

    scenarios = build_scenarios()
    cases = build_cases(args, scenarios)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    client_cache: dict[tuple[str, str], Any] = {}
    results: list[dict[str, Any]] = []
    started_at = datetime.now(timezone.utc).isoformat()

    for case in cases:
        client_key = (case.base_url, case.region)
        if client_key not in client_cache:
            client_cache[client_key] = new_client(
                api_key=settings.ark_api_key,
                base_url=case.base_url,
                region=case.region,
                timeout_seconds=args.timeout_seconds,
                connect_timeout_seconds=args.connect_timeout_seconds,
                max_retries=args.max_retries,
            )
        client = client_cache[client_key]
        for run_index in range(1, args.runs + 1):
            result = run_once(client, case)
            result["run_index"] = run_index
            results.append(result)
            status = "ok" if result["success"] else f"error:{result['error_type']}"
            print(
                f"[{status}] {case.scenario.name} model={case.model} "
                f"tokens={case.max_tokens} temp={case.temperature} "
                f"first={result['first_chunk_ms']} total={result['total_ms']}"
            )

    summary_rows = summarize(results)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"doubao_latency_{timestamp}.json"
    payload = {
        "started_at": started_at,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "region": args.region,
        "runs_per_case": args.runs,
        "results": results,
        "summary": summary_rows,
        "notes": [
            "No API key, full prompt, health profile, or image payload is stored.",
            "Prompt metrics include only character count and message count.",
        ],
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print_markdown_table(summary_rows)
    print()
    print(f"JSON result: {output_path}")
    if args.csv:
        csv_path = output_path.with_suffix(".summary.csv")
        write_csv(csv_path, summary_rows)
        print(f"CSV summary: {csv_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
