import argparse
import subprocess
import sys

from app.core.cities import get_city


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("Limits must be positive integers.")
    return parsed


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run place and image collection for an entire CityBuddy city."
    )
    parser.add_argument("--city", default="turin")
    parser.add_argument("--place-limit-per-category", type=positive_integer)
    parser.add_argument("--image-limit", type=positive_integer)
    parser.add_argument(
        "--trigger",
        choices=("manual", "scheduled"),
        default="manual",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write both collections to staging. Production is never promoted.",
    )
    return parser.parse_args()


def build_commands(arguments: argparse.Namespace) -> list[list[str]]:
    base = ["--city", arguments.city, "--trigger", arguments.trigger]
    place_command = [
        sys.executable,
        "-m",
        "scripts.collect_osm_staging",
        *base,
    ]
    image_command = [
        sys.executable,
        "-m",
        "scripts.collect_wikimedia_staging",
        *base,
    ]
    if arguments.place_limit_per_category:
        place_command.extend(
            ["--limit-per-category", str(arguments.place_limit_per_category)]
        )
    if arguments.image_limit:
        image_command.extend(["--limit", str(arguments.image_limit)])
    if arguments.apply:
        place_command.append("--apply")
        image_command.append("--apply")
    return [place_command, image_command]


def main() -> None:
    arguments = parse_arguments()
    get_city(arguments.city)
    for command in build_commands(arguments):
        print(f"Running: {' '.join(command)}")
        subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
