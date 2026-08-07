import unittest
from urllib.parse import parse_qs, urlparse

from app.core.maps import (
    GOOGLE_MAPS_TRANSIT_DISCLAIMER,
    get_google_maps_transit_url,
)


class GoogleMapsTests(unittest.TestCase):
    def test_transit_url_is_key_free_and_grounded(self) -> None:
        url = get_google_maps_transit_url(45.0703, 7.6869)
        query = parse_qs(urlparse(url).query)

        self.assertEqual(query["api"], ["1"])
        self.assertEqual(query["destination"], ["45.0703,7.6869"])
        self.assertEqual(query["travelmode"], ["transit"])
        self.assertNotIn("key", query)

    def test_disclaimer_requires_current_information_to_be_verified(self) -> None:
        self.assertIn("may change", GOOGLE_MAPS_TRANSIT_DISCLAIMER)
        self.assertIn("verify", GOOGLE_MAPS_TRANSIT_DISCLAIMER)


if __name__ == "__main__":
    unittest.main()
