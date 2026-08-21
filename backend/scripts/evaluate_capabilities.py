import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

from app.llm.capability_evaluation import (
    DEFAULT_CAPABILITY_DATASET,
    capability_dataset_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and summarize the CityBuddy production capability benchmark. "
            "Live tool/RAG execution is added incrementally on top of this frozen fixture."
        )
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_CAPABILITY_DATASET)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("evaluation/results/capability"),
    )
    arguments = parser.parse_args()

    report = capability_dataset_report(arguments.dataset)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    output = arguments.output_dir / f"capability-dataset-{datetime.now():%Y%m%d-%H%M%S}.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Capability dataset: {report['total_cases']} cases")
    print(f"Capabilities: {report['capabilities']}")
    print(f"Requirements: {report['requirements']}")
    print(f"JSON report: {output}")


if __name__ == "__main__":
    main()
