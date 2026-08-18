import unittest

from app.core.ingestion import (
    build_candidate_fingerprint,
    missing_enrichment_updates,
    validate_image_candidate,
    validate_place_candidate,
    validation_status,
)


def valid_candidate() -> dict:
    return {
        "source": "osm",
        "source_id": "node/123",
        "name": "Test Museum",
        "category": "museum",
        "address": "Via Roma 1",
        "city": "Torino",
        "country_code": "IT",
        "latitude": 45.07,
        "longitude": 7.68,
        "website": "https://example.org",
        "lifecycle_tags": [],
    }


def valid_image_candidate() -> dict:
    return {
        "place_id": 10,
        "wikidata_id": "Q123",
        "source": "wikimedia_commons",
        "source_image_id": "File:Example.jpg",
        "image_url": "https://upload.wikimedia.org/example.jpg",
        "thumbnail_url": "https://upload.wikimedia.org/thumb/example.jpg",
        "source_page_url": "https://commons.wikimedia.org/wiki/File:Example.jpg",
        "attribution": "Example photographer",
        "license": "CC BY-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-sa/4.0",
    }


class IngestionValidationTests(unittest.TestCase):
    def test_valid_candidate_is_eligible_for_review(self) -> None:
        findings = validate_place_candidate(valid_candidate())
        self.assertEqual(findings, [])
        self.assertEqual(validation_status(findings), "valid")

    def test_unsupported_category_is_invalid(self) -> None:
        candidate = valid_candidate()
        candidate["category"] = "train_station"

        findings = validate_place_candidate(candidate)

        self.assertEqual(validation_status(findings), "invalid")
        self.assertIn(
            "unsupported_category",
            {finding.code for finding in findings},
        )

    def test_invalid_coordinates_and_website_are_rejected(self) -> None:
        candidate = valid_candidate()
        candidate["latitude"] = 95
        candidate["website"] = "javascript:alert(1)"

        findings = validate_place_candidate(candidate)
        codes = {finding.code for finding in findings}

        self.assertEqual(validation_status(findings), "invalid")
        self.assertIn("invalid_latitude", codes)
        self.assertIn("invalid_website", codes)

    def test_lifecycle_metadata_requires_explicit_review(self) -> None:
        candidate = valid_candidate()
        candidate["lifecycle_tags"] = ["disused:amenity=museum"]

        findings = validate_place_candidate(candidate)

        self.assertEqual(validation_status(findings), "review_required")
        self.assertEqual(findings[0].severity, "warning")

    def test_missing_address_requires_review(self) -> None:
        candidate = valid_candidate()
        candidate["address"] = "Address unavailable"

        findings = validate_place_candidate(candidate)

        self.assertEqual(validation_status(findings), "review_required")
        self.assertIn(
            "missing_address_review_required",
            {finding.code for finding in findings},
        )

    def test_temporary_name_requires_review(self) -> None:
        candidate = valid_candidate()
        candidate["name"] = "Temporary Museum"

        findings = validate_place_candidate(candidate)

        self.assertEqual(validation_status(findings), "review_required")

    def test_valid_commons_image_passes_validation(self) -> None:
        findings = validate_image_candidate(valid_image_candidate())
        self.assertEqual(findings, [])

    def test_image_requires_commons_hosts_and_attribution(self) -> None:
        candidate = valid_image_candidate()
        candidate["image_url"] = "https://example.com/image.jpg"
        candidate["attribution"] = ""

        findings = validate_image_candidate(candidate)
        codes = {finding.code for finding in findings}

        self.assertEqual(validation_status(findings), "invalid")
        self.assertIn("invalid_image_url", codes)
        self.assertIn("missing_attribution", codes)

    def test_image_requires_valid_wikidata_and_file_ids(self) -> None:
        candidate = valid_image_candidate()
        candidate["wikidata_id"] = "not-wikidata"
        candidate["source_image_id"] = "Example.jpg"

        findings = validate_image_candidate(candidate)
        codes = {finding.code for finding in findings}

        self.assertIn("invalid_wikidata_id", codes)
        self.assertIn("invalid_source_image_id", codes)


    def test_enrichment_only_fills_missing_production_fields(self) -> None:
        current = {
            "description": None,
            "opening_hours": "Mo-Fr 09:00-17:00",
            "website": "",
            "operator": "Existing operator",
        }
        candidate = {
            "description": "A reviewed museum description.",
            "opening_hours": "24/7",
            "website": "https://example.org",
            "operator": "Different operator",
        }

        updates = missing_enrichment_updates(current, candidate)

        self.assertEqual(
            updates,
            {
                "description": "A reviewed museum description.",
                "website": "https://example.org",
            },
        )

    def test_enrichment_ignores_empty_source_values(self) -> None:
        updates = missing_enrichment_updates(
            {"description": None, "website": None},
            {"description": "", "website": None},
        )

        self.assertEqual(updates, {})

    def test_fingerprint_is_stable_across_key_order(self) -> None:
        first = {"source_id": "node/123", "name": "Museum"}
        second = {"name": "Museum", "source_id": "node/123"}

        self.assertEqual(
            build_candidate_fingerprint(first),
            build_candidate_fingerprint(second),
        )

    def test_fingerprint_changes_with_source_data(self) -> None:
        candidate = valid_candidate()
        original = build_candidate_fingerprint(candidate)
        candidate["name"] = "Renamed Museum"

        self.assertNotEqual(original, build_candidate_fingerprint(candidate))


if __name__ == "__main__":
    unittest.main()
