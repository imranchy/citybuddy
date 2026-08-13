import argparse
import json

from app.api.routes.assistant import get_assistant_service
from app.db.database import SessionLocal
from app.schemas.assistant import AssistantChatRequest


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run one grounded CityBuddy assistant query without the frontend."
    )
    parser.add_argument("message", help="Natural-language CityBuddy request.")
    parser.add_argument("--language", choices=("en", "it"), default="en")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--radius-km", type=float)
    parser.add_argument(
        "--context-place-id", dest="context_place_ids", type=int, action="append"
    )
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    request = AssistantChatRequest(
        message=arguments.message,
        language=arguments.language,
        latitude=arguments.latitude,
        longitude=arguments.longitude,
        radius_km=arguments.radius_km,
        context_place_ids=arguments.context_place_ids or [],
    )
    with SessionLocal() as database:
        response = get_assistant_service().respond(database, request)
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
