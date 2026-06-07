#!/usr/bin/env python3
"""Model benchmarking harness.

Runs a fixed set of test messages through each model and reports:
  - JSON parse success rate
  - Average latency per message (seconds)
  - Category accuracy against the expected fixture
  - Total wall-clock time

Results are printed as a Markdown table and saved to data/bench_results.json.

Usage:
    uv run python scripts/bench_models.py
    uv run python scripts/bench_models.py --models llama3.2:3b phi4-mini
    uv run python scripts/bench_models.py --fixture tests/fixtures/sample_inbox.json

    # To use a cloud OpenAI-compatible endpoint instead of Ollama:
    uv run python scripts/bench_models.py --backend openai --base-url https://api.openai.com/v1
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path
from dataclasses import dataclass, field, asdict
from typing import Any

# ---------------------------------------------------------------------------
# Default models to benchmark
# ---------------------------------------------------------------------------

DEFAULT_MODELS = [
    "llama3.2:3b",
    "qwen2.5:3b",
    "phi4-mini",
    "llama3.1:8b",
]

# ---------------------------------------------------------------------------
# Built-in sample inbox (used when no --fixture is provided)
# ---------------------------------------------------------------------------

SAMPLE_INBOX: list[dict[str, Any]] = [
    {
        "id": "bench_001",
        "subject": "Quick question about the Q3 report",
        "sender": "alice@company.com",
        "body_preview": "Hi, do you have the Q3 numbers ready? I need them for the board deck by Friday.",
        "expected_category": "needs_reply",
    },
    {
        "id": "bench_002",
        "subject": "Your invoice #4821 is due",
        "sender": "billing@supplier.com",
        "body_preview": "Please pay invoice #4821 for $1,200 by 15 July to avoid late fees.",
        "expected_category": "needs_action",
    },
    {
        "id": "bench_003",
        "subject": "Re: Proposal review",
        "sender": "bob@client.com",
        "body_preview": "Thanks for sending the proposal. I've forwarded it to our legal team and will get back to you next week.",
        "expected_category": "waiting_on",
    },
    {
        "id": "bench_004",
        "subject": "GitHub Actions build failed",
        "sender": "notifications@github.com",
        "body_preview": "Your workflow 'CI' failed on branch main. View the run for details.",
        "expected_category": "fyi",
    },
    {
        "id": "bench_005",
        "subject": "Team lunch next Thursday",
        "sender": "manager@company.com",
        "body_preview": "We'll be doing a team lunch on Thursday at noon. No action needed, just a heads-up.",
        "expected_category": "fyi",
    },
    {
        "id": "bench_006",
        "subject": "Follow up: contract renewal",
        "sender": "sales@vendor.com",
        "body_preview": "Just circling back on the contract renewal we discussed. No rush but wanted to stay on your radar.",
        "expected_category": "follow_up",
    },
]

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class MessageResult:
    message_id: str
    expected: str
    predicted: str | None
    latency_s: float
    parse_ok: bool


@dataclass
class ModelResult:
    model: str
    message_results: list[MessageResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.message_results)

    @property
    def parse_success_rate(self) -> float:
        if not self.total:
            return 0.0
        return sum(1 for r in self.message_results if r.parse_ok) / self.total

    @property
    def accuracy(self) -> float:
        parsed = [r for r in self.message_results if r.parse_ok]
        if not parsed:
            return 0.0
        return sum(1 for r in parsed if r.predicted == r.expected) / len(parsed)

    @property
    def avg_latency(self) -> float:
        if not self.total:
            return 0.0
        return sum(r.latency_s for r in self.message_results) / self.total

    @property
    def total_time(self) -> float:
        return sum(r.latency_s for r in self.message_results)


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def _call_ollama(model: str, prompt: str, base_url: str) -> tuple[str, float, bool]:
    """Call Ollama and return (response_text, latency_s, parse_ok).
    
    Requires `ollama` Python package: `uv add ollama --dev`
    Falls back to httpx raw call if package not available.
    """
    import httpx
    import json as _json

    t0 = time.monotonic()
    try:
        resp = httpx.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "format": "json",
                "options": {"temperature": 0.1, "num_ctx": 2048},
            },
            timeout=120.0,
        )
        latency = time.monotonic() - t0
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        # Try to parse the response as JSON
        data = _json.loads(raw)
        category = data.get("category") or (
            data.get("items", [{}])[0].get("category") if data.get("items") else None
        )
        return category or "", latency, True
    except Exception as exc:  # noqa: BLE001
        latency = time.monotonic() - t0
        print(f"  [ERROR] {model}: {exc}")
        return "", latency, False


def _triage_prompt(msg: dict[str, Any]) -> str:
    return (
        f"Classify this email into one of: needs_reply, needs_action, waiting_on, follow_up, fyi.\n"
        f"Return ONLY valid JSON: {{\"category\": \"<value>\"}}.\n"
        f"Subject: {msg['subject']}\n"
        f"From: {msg['sender']}\n"
        f"Body: {msg['body_preview']}"
    )


def run_benchmark(
    models: list[str],
    messages: list[dict[str, Any]],
    backend: str = "ollama",
    base_url: str = "http://localhost:11434",
) -> list[ModelResult]:
    results: list[ModelResult] = []

    for model in models:
        print(f"\nBenchmarking: {model}")
        model_result = ModelResult(model=model)

        for msg in messages:
            prompt = _triage_prompt(msg)
            predicted, latency, parse_ok = _call_ollama(model, prompt, base_url)
            model_result.message_results.append(
                MessageResult(
                    message_id=msg["id"],
                    expected=msg["expected_category"],
                    predicted=predicted,
                    latency_s=latency,
                    parse_ok=parse_ok,
                )
            )
            status = "OK" if parse_ok else "FAIL"
            match = "✓" if predicted == msg["expected_category"] else "✗"
            print(f"  [{status}] {msg['id']} {match} ({latency:.1f}s) predicted={predicted!r}")

        results.append(model_result)

    return results


def print_table(results: list[ModelResult]) -> None:
    print("\n" + "=" * 72)
    print("BENCHMARK RESULTS")
    print("=" * 72)
    header = f"{'Model':<25} {'Parse%':>7} {'Accuracy':>9} {'Avg(s)':>7} {'Total(s)':>9}"
    print(header)
    print("-" * 72)
    for r in results:
        print(
            f"{r.model:<25} "
            f"{r.parse_success_rate * 100:>6.0f}% "
            f"{r.accuracy * 100:>8.0f}% "
            f"{r.avg_latency:>7.1f} "
            f"{r.total_time:>9.1f}"
        )
    print("=" * 72)


def save_results(results: list[ModelResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    data = [
        {
            "model": r.model,
            "parse_success_rate": r.parse_success_rate,
            "accuracy": r.accuracy,
            "avg_latency_s": r.avg_latency,
            "total_time_s": r.total_time,
            "messages": [asdict(mr) for mr in r.message_results],
        }
        for r in results
    ]
    output_path.write_text(json.dumps(data, indent=2))
    print(f"\nResults saved to {output_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark LLM models for email triage.")
    parser.add_argument(
        "--models",
        nargs="+",
        default=DEFAULT_MODELS,
        help="Space-separated list of Ollama model tags to benchmark.",
    )
    parser.add_argument(
        "--fixture",
        type=Path,
        default=None,
        help="Path to a JSON file with test messages (list of {id, subject, sender, body_preview, expected_category}).",
    )
    parser.add_argument(
        "--backend",
        default="ollama",
        choices=["ollama"],
        help="LLM backend to use (currently only 'ollama' is supported).",
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:11434",
        help="Base URL of the Ollama API.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("data/bench_results.json"),
        help="Path to save JSON results.",
    )
    args = parser.parse_args()

    messages = SAMPLE_INBOX
    if args.fixture:
        messages = json.loads(args.fixture.read_text())

    print(f"Benchmarking {len(args.models)} model(s) on {len(messages)} message(s).")

    results = run_benchmark(
        models=args.models,
        messages=messages,
        backend=args.backend,
        base_url=args.base_url,
    )
    print_table(results)
    save_results(results, args.output)


if __name__ == "__main__":
    main()
