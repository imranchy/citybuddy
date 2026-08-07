import unittest

from app.core.cities import get_city
from app.core.place_catalog import (
    CATEGORY_GROUP_LABELS,
    DESTINATION_CATEGORIES,
    get_category,
    get_osm_filters,
    group_categories,
)


class CityConfigTests(unittest.TestCase):
    def test_city_alias_resolves_to_turin(self) -> None:
        city = get_city("Torino")
        self.assertEqual(city.key, "turin")
        self.assertEqual(city.country_code, "IT")
        self.assertEqual(city.default_language, "it")
        self.assertEqual(city.timezone, "Europe/Rome")
        self.assertEqual(city.overpass_bounding_box, "44.958,7.577,45.133,7.773")

    def test_unknown_city_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unsupported city"):
            get_city("unknown")


class PlaceCatalogTests(unittest.TestCase):
    def test_catalog_covers_broad_discovery_categories(self) -> None:
        expected = {
            "restaurant", "museum", "park", "nightclub", "market",
            "library", "mosque", "church", "hotel",
        }
        self.assertTrue(expected.issubset(DESTINATION_CATEGORIES))
        self.assertNotIn("train_station", DESTINATION_CATEGORIES)

    def test_grouped_categories_use_stable_product_order(self) -> None:
        groups = group_categories({"mosque", "restaurant", "museum"})
        self.assertEqual(
            [group["label"] for group in groups],
            ["Food & Drink", "Culture & Attractions", "Places of Worship"],
        )
        self.assertEqual(len(CATEGORY_GROUP_LABELS), 8)

    def test_places_of_worship_are_normalized(self) -> None:
        self.assertEqual(
            get_category({"amenity": "place_of_worship", "religion": "muslim"}),
            "mosque",
        )
        self.assertEqual(
            get_category({"amenity": "place_of_worship", "religion": "sikh"}),
            "gurdwara",
        )
        self.assertEqual(
            get_category({"amenity": "place_of_worship"}),
            "place_of_worship",
        )

    def test_transport_tags_are_not_discovery_categories(self) -> None:
        self.assertIsNone(get_category({"highway": "bus_stop"}))
        self.assertIsNone(get_category({"railway": "station"}))

    def test_tourist_information_requires_office_subtype(self) -> None:
        self.assertEqual(
            get_category({"tourism": "information", "information": "office"}),
            "tourist_information",
        )
        self.assertIsNone(
            get_category({"tourism": "information", "information": "board"})
        )

    def test_category_filtering_returns_only_requested_filters(self) -> None:
        self.assertEqual(
            get_osm_filters(category="library"),
            ('["amenity"="library"]["name"]',),
        )


if __name__ == "__main__":
    unittest.main()
