import unittest

from app.core.overpass import OVERPASS_URLS


class OverpassConfigurationTests(unittest.TestCase):
    def test_current_free_fallbacks_are_configured(self) -> None:
        self.assertIn(
            "https://overpass.private.coffee/api/interpreter",
            OVERPASS_URLS,
        )
        self.assertIn(
            "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            OVERPASS_URLS,
        )
        self.assertNotIn(
            "https://overpass.kumi.systems/api/interpreter",
            OVERPASS_URLS,
        )


if __name__ == "__main__":
    unittest.main()
