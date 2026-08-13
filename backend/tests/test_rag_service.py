import unittest
from types import SimpleNamespace

from app.services.rag import build_place_evidence


class RagServiceTests(unittest.TestCase):
    def test_reviewed_place_fields_form_attributed_evidence(self) -> None:
        place = SimpleNamespace(
            id=7,
            name="Museo Cinema",
            category="museum",
            address="Via Test 1",
            city="Torino",
            country_code="IT",
            description="A film collection.",
            operator=None,
            opening_hours="Tu-Su 10:00-18:00",
            dietary_options=[],
            website="https://example.test",
            source="osm",
            source_id="node/7",
        )

        evidence = build_place_evidence(place)

        self.assertIn("A film collection", evidence.content)
        self.assertIn("Recorded opening hours", evidence.content)
        self.assertEqual(evidence.attribution, "OpenStreetMap contributors")
        self.assertEqual(evidence.license, "ODbL")
        self.assertEqual(evidence.source_url, "https://www.openstreetmap.org/node/7")
        self.assertEqual(len(evidence.fingerprint), 64)


if __name__ == "__main__":
    unittest.main()
