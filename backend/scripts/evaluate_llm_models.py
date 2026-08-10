import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from app.llm.evaluation import evaluate_model
from app.llm.ollama import OllamaProvider
from app.llm.tracing import TraceConfig


DEFAULT_MODELS = (
    "gemma3:4b",
    "llama3.1:8b",
    "qwen3:8b",
    "gemma3:12b-it-qat",
)


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Timeout must be greater than zero.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate local models against CityBuddy requirements."
    )
    parser.add_argument(
        "--model",
        dest="models",
        action="append",
        help="Ollama model name; repeat to compare models.",
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=positive_float, default=120.0)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("artifacts"),
    )
    parser.add_argument(
        "--langsmith",
        action="store_true",
        help="Send synthetic evaluation traces to LangSmith (opt-in).",
    )
    parser.add_argument(
        "--langsmith-project",
        help="Override LANGSMITH_PROJECT for this evaluation run.",
    )
    return parser.parse_args()


def markdown_report(report: dict[str, Any]) -> str:
    lines = [
        "# CityBuddy local-model evaluation",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "| Model | Strict cases | Field accuracy | Grounding | Supported claims | Evidence coverage | Errors | Warm p95 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for result in report["models"]:
        metrics = result["metrics"]
        latency = result["latency"]["warm_p95_ms"]
        latency_text = "n/a" if latency is None else f"{latency / 1000:.2f} s"
        supported = metrics["supported_claim_rate_percent"]
        evidence = result["claim_evidence"]
        supported_text = (
            f"n/a ({evidence['supported_claims']}/{evidence['total_claims']})"
            if supported is None
            else f"{supported}% ({evidence['supported_claims']}/{evidence['total_claims']})"
        )
        coverage = metrics["recommendation_evidence_coverage_percent"]
        coverage_text = (
            "n/a"
            if coverage is None
            else f"{coverage}% ({evidence['recommendations_with_evidence']}/{evidence['recommendations']})"
        )
        lines.append(
            f"| `{result['model']}` | {result['passed_cases']}/"
            f"{result['total_cases']} | {metrics['field_accuracy_percent']}% | "
            f"{metrics['grounding_check_accuracy_percent']}% | {supported_text} | "
            f"{coverage_text} | {result['errors']['total']} | {latency_text} |"
        )
    for result in report["models"]:
        lines.extend(["", f"## {result['model']}", ""])
        for case in result["cases"]:
            marker = "PASS" if case["passed"] else "FAIL"
            detail = case.get("error")
            if detail is None:
                failed_checks = [
                    name for name, passed in case["checks"].items() if not passed
                ]
                detail = "all checks" if not failed_checks else ", ".join(failed_checks)
            lines.append(f"- {marker} `{case['key']}` — {detail}")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    load_dotenv()
    arguments = parse_arguments()
    models = tuple(arguments.models or DEFAULT_MODELS)
    provider = OllamaProvider(
        base_url=arguments.ollama_url,
        timeout_seconds=arguments.timeout,
    )
    trace_config = TraceConfig.from_environment(
        enabled=arguments.langsmith,
        project=arguments.langsmith_project,
    )
    results = []
    for model in models:
        print(f"Evaluating {model}...")
        result = evaluate_model(provider, model=model, trace_config=trace_config)
        results.append(result)
        print(
            f"  {result['passed_cases']}/{result['total_cases']} passed; "
            f"strict {result['score_percent']}%; "
            f"field {result['metrics']['field_accuracy_percent']}%; "
            f"grounding {result['metrics']['grounding_check_accuracy_percent']}%; "
            f"errors {result['errors']['total']}; "
            f"warm p95 {result['latency']['warm_p95_ms']} ms"
        )
        try:
            provider.unload_model(model)
        except Exception as error:
            print(f"  Warning: {error}")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "ollama_url": arguments.ollama_url,
        "langsmith": {
            "enabled": trace_config.enabled,
            "project": trace_config.project if trace_config.enabled else None,
        },
        "models": results,
    }
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    json_path = arguments.output_dir / f"llm-evaluation-{timestamp}.json"
    markdown_path = arguments.output_dir / f"llm-evaluation-{timestamp}.md"
    json_path.write_text(
        json.dumps(report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    markdown_path.write_text(markdown_report(report), encoding="utf-8")
    print(f"JSON report: {json_path}")
    print(f"Readable report: {markdown_path}")


if __name__ == "__main__":
    main()
