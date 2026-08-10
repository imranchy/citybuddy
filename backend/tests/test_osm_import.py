import argparse
import unittest

from scripts.import_osm_places import (
    filter_candidates_by_source_ids,
    get_lifecycle_tags,
    get_osm_filter_batches,
    get_operational_metadata,
    parse_osm_source_id,
    validate_refresh_request,
)

class OsmSourceSelectionTests(unittest.TestCase):
    def test_all_category_filters_are_batched_by_product_group(self) -> None:
        batches = get_osm_filter_batches(category=None)
        group_names = [group_name for group_name, _ in batches]
        filters = [
            osm_filter
            for _, group_filters in batches
            for osm_filter in group_filters
        ]

        self.assertEqual(len(batches), 8)
        self.assertEqual(len(group_names), len(set(group_names)))
        self.assertEqual(len(filters), len(set(filters)))
        self.assertIn('["tourism"="museum"]["name"]', filters)
        self.assertIn('["tourism"="hotel"]["name"]', filters)

    def test_single_category_uses_one_source_batch(self) -> None:
        self.assertEqual(
            get_osm_filter_batches(category="museum"),
            (("museum", ('["tourism"="museum"]["name"]',)),),
        )

    def test_filter_keeps_only_requested_source_ids(self) -> None:
        candidates = [
            (
                {"type": "node", "id": 100},
                "First market",
                "market",
                7.1,
                45.1,
            ),
            (
                {"type": "way", "id": 200},
                "Second market",
                "market",
                7.2,
                45.2,
            ),
        ]

        filtered = filter_candidates_by_source_ids(
            candidates,
            frozenset({"way/200"}),
        )

        self.assertEqual(filtered, [candidates[1]])

    def test_refresh_requires_source_allowlist(self) -> None:
        with self.assertRaisesRegex(
            ValueError,
            "requires at least one --source-id",
        ):
            validate_refresh_request(True, None)

        validate_refresh_request(
            True,
            frozenset({"node/100"}),
        )
        validate_refresh_request(False, None)


    def test_lifecycle_tags_are_reported(self) -> None:
        tags = {
            "name": "Former market",
            "disused:amenity": "marketplace",
            "opening_hours": "closed",
            "abandoned": "yes",
        }

        self.assertEqual(
            get_lifecycle_tags(tags),
            [
                "abandoned=yes",
                "disused:amenity=marketplace",
            ],
        )

    def test_operational_metadata_uses_contact_website_fallback(
        self,
    ) -> None:
        tags = {
            "opening_hours": "Mo-Sa 08:00-14:00",
            "contact:website": "https://example.com/market",
            "operator": "Comune di Torino",
        }

        self.assertEqual(
            get_operational_metadata(tags),
            {
                "opening_hours": "Mo-Sa 08:00-14:00",
                "website": "https://example.com/market",
                "operator": "Comune di Torino",
            },
        )

    def test_no_allowlist_preserves_all_candidates(self) -> None:
        candidates = [
            (
                {"type": "node", "id": 100},
                "Market",
                "market",
                7.1,
                45.1,
            ),
        ]

        self.assertEqual(
            filter_candidates_by_source_ids(candidates, None),
            candidates,
        )

    def test_source_id_is_normalized(self) -> None:
        self.assertEqual(
            parse_osm_source_id(" Way/123 "),
            "way/123",
        )

    def test_invalid_source_id_is_rejected(self) -> None:
        with self.assertRaises(argparse.ArgumentTypeError):
            parse_osm_source_id("market-123")


if __name__ == "__main__":
    unittest.main()
