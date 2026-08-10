import unittest
from argparse import Namespace

from app.core.ingestion import limit_candidates_per_category
from scripts.run_city_collection import build_commands


class CollectionLimitTests(unittest.TestCase):
    def test_limit_is_applied_independently_to_each_category(self) -> None:
        candidates = [
            {"category": "cafe", "name": "A"},
            {"category": "cafe", "name": "B"},
            {"category": "museum", "name": "C"},
            {"category": "museum", "name": "D"},
        ]

        limited = limit_candidates_per_category(candidates, 1)

        self.assertEqual(
            limited,
            [
                {"category": "cafe", "name": "A"},
                {"category": "museum", "name": "C"},
            ],
        )

    def test_city_collection_never_invokes_promotion(self) -> None:
        arguments = Namespace(
            city="turin",
            trigger="scheduled",
            place_limit_per_category=25,
            image_limit=40,
            apply=True,
        )

        commands = build_commands(arguments)
        flattened = " ".join(part for command in commands for part in command)

        self.assertIn("scripts.collect_osm_staging", flattened)
        self.assertIn("scripts.collect_wikimedia_staging", flattened)
        self.assertNotIn("promote", flattened)
        self.assertEqual(sum("--apply" in command for command in commands), 2)


if __name__ == "__main__":
    unittest.main()
