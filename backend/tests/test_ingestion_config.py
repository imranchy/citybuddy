import unittest

from app.core.cities import get_city
from app.core.place_catalog import (
    DESTINATION_CATEGORIES,
    TRANSPORT_CATEGORIES,
    get_category,
    get_osm_filters,
)


class CityConfigTests(unittest.TestCase):
    def test_city_alias_resolves_to_turin(self) -> None:
        city = get_city("Torino")

        self.assertEqual(city.key, "turin")
        self.assertEqual(city.country_code, "IT")
        self.assertEqual(city.default_language, "it")
        self.assertEqual(city.timezone, "Europe/Rome")
        self.assertEqual(
            city.overpass_bounding_box,
            "44.958,7.577,45.133,7.773",
        )

    def test_unknown_city_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported city"):
            get_city("unknown")


class PlaceCatalogTests(unittest.TestCase):
    def test_destination_and_transport_categories_are_separate(self) -> None:
        self.assertTrue(
            DESTINATION_CATEGORIES.isdisjoint(TRANSPORT_CATEGORIES)
        )

    def test_destination_categories_include_tourism_priorities(self) -> None:
        self.assertTrue(
            {
                "restaurant",
                "library",
                "hotel",
                "viewpoint",
                "tourist_information",
            }.issubset(DESTINATION_CATEGORIES)
        )

    def test_tourist_information_requires_office_subtype(self) -> None:
        self.assertEqual(
            get_category(
                {
                    "tourism": "information",
                    "information": "office",
                }
            ),
            "tourist_information",
        )
        self.assertIsNone(
            get_category(
                {
                    "tourism": "information",
                    "information": "board",
                }
            )
        )
        self.assertEqual(
            get_osm_filters(
                layer="destination",
                category="tourist_information",
            ),
            (
                '["tourism"="information"]'
                '["information"="office"]["name"]',
            ),
        )

    def test_transport_tags_are_normalized(self) -> None:
        self.assertEqual(
            get_category(
                {
                    "highway": "bus_stop",
                    "operator": "FlixBus",
                }
            ),
            "coach_stop",
        )
        self.assertEqual(
            get_category(
                {
                    "railway": "station",
                    "station": "subway",
                }
            ),
            "metro_station",
        )

    def test_category_filtering_returns_only_requested_filters(self) -> None:
        filters = get_osm_filters(
            layer="destination",
            category="library",
        )

        self.assertEqual(
            filters,
            ('["amenity"="library"]["name"]',),
        )


if __name__ == "__main__":
    unittest.main()
