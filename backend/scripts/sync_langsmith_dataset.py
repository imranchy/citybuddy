import argparse
import json
from pathlib import Path

from dotenv import load_dotenv


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Explicitly synchronize a versioned CityBuddy dataset to LangSmith."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("evaluation/datasets/legacy/conversations-v1.json"),
    )
    arguments = parser.parse_args()
    load_dotenv()
    from langsmith import Client

    payload = json.loads(arguments.dataset.read_text(encoding="utf-8"))
    client = Client()
    if client.has_dataset(dataset_name=payload["name"]):
        dataset = client.read_dataset(dataset_name=payload["name"])
    else:
        dataset = client.create_dataset(
            dataset_name=payload["name"],
            description=f"CityBuddy versioned evaluation dataset v{payload['version']}",
        )
    existing = {
        example.metadata.get("case_key"): example
        for example in client.list_examples(dataset_id=dataset.id)
        if example.metadata
    }
    created = updated = 0
    for case in payload["cases"]:
        metadata = {
            "case_key": case["key"],
            "dataset_version": payload["version"],
            "source": str(arguments.dataset),
        }
        current = existing.get(case["key"])
        if current is None:
            client.create_example(
                dataset_id=dataset.id,
                inputs=case["inputs"],
                outputs=case["outputs"],
                metadata=metadata,
            )
            created += 1
        else:
            client.update_example(
                current.id,
                inputs=case["inputs"],
                outputs=case["outputs"],
                metadata=metadata,
            )
            updated += 1
    print(f"LangSmith dataset '{payload['name']}': {created} created, {updated} updated.")


if __name__ == "__main__":
    main()
