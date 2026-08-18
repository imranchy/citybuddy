import argparse
import json
from time import perf_counter

from app.llm.ollama import OllamaProvider
from app.llm.prompts import ASSISTANT_RESPONSE_SYSTEM_PROMPT
from app.llm.schemas import GroundedResponse


CASES = (
    ("en", "English"),
    ("it", "Italian"),
    ("pt", "Portuguese"),
    ("de", "German"),
    ("bn", "Bangla"),
)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Manually inspect direct multilingual CityBuddy response quality using the "
            "existing Ollama response model. No translation model is involved."
        )
    )
    parser.add_argument("--model", default="gemma3:12b-it-qat")
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=float, default=120.0)
    return parser.parse_args()


def prompt(language: str, language_name: str) -> str:
    return json.dumps(
        {
            "conversation_history": [],
            "current_user_message": "Recommend one museum in Turin and explain why it fits.",
            "validated_intent": {
                "city": "turin",
                "categories": ["museum"],
                "limit": 1,
                "nearby": False,
                "radius_km": None,
                "wants_transport": False,
                "language": language,
                "unsupported_constraints": [],
            },
            "required_response_language": language,
            "required_response_language_name": language_name,
            "retrieved_records": [
                {
                    "id": 7,
                    "name": "Museo Test",
                    "category": "museum",
                    "description": "A reviewed museum with a cinema collection.",
                    "address": "Via Test 1",
                    "city": "Torino",
                    "country_code": "IT",
                    "latitude": 45.07,
                    "longitude": 7.68,
                    "price_level": None,
                    "rating": None,
                    "dietary_options": [],
                    "opening_hours": None,
                    "website": None,
                    "operator": None,
                }
            ],
            "retrieved_evidence": [],
        },
        ensure_ascii=False,
    )


def main() -> None:
    arguments = parse_arguments()
    provider = OllamaProvider(
        base_url=arguments.ollama_url,
        timeout_seconds=arguments.timeout,
    )
    print(f"Model: {arguments.model}")
    print("Input message stays English; only the selected output language changes.\n")
    for language, language_name in CASES:
        started = perf_counter()
        result = provider.generate_structured(
            model=arguments.model,
            system_prompt=ASSISTANT_RESPONSE_SYSTEM_PROMPT,
            user_prompt=prompt(language, language_name),
            output_schema=GroundedResponse,
        )
        elapsed = perf_counter() - started
        output = GroundedResponse.model_validate(result.output)
        reason = output.recommendations[0].reason if output.recommendations else "<none>"
        print(f"[{language} / {language_name}] {elapsed:.2f}s")
        print(f"summary: {output.summary}")
        print(f"reason:  {reason}")
        print()


if __name__ == "__main__":
    main()
