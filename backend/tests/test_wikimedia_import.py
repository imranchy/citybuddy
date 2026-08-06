import argparse
import unittest

from scripts.import_wikimedia_images import (
    filter_wikidata_mappings,
    parse_wikidata_id,
)


class WikidataSelectionTests(unittest.TestCase):
    def test_filter_keeps_only_requested_wikidata_ids(self) -> None:
        mappings = {
            "node/1": "Q100",
            "way/2": "Q200",
            "relation/3": "Q300",
        }

        filtered = filter_wikidata_mappings(
            mappings,
            frozenset({"Q100", "Q300"}),
        )

        self.assertEqual(
            filtered,
            {
                "node/1": "Q100",
                "relation/3": "Q300",
            },
        )

    def test_no_allowlist_preserves_all_mappings(self) -> None:
        mappings = {
            "node/1": "Q100",
            "way/2": "Q200",
        }

        self.assertEqual(
            filter_wikidata_mappings(mappings, None),
            mappings,
        )

    def test_wikidata_id_is_normalized(self) -> None:
        self.assertEqual(parse_wikidata_id(" q123 "), "Q123")

    def test_invalid_wikidata_id_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_wikidata_id("not-an-id")


if __name__ == "__main__":
    unittest.main()