import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.schemas.place import PlaceRead
from app.services.place_types import RetrievedPlace
from app.tools.citybuddy import PlaceSearchInput, get_place, normalize_tool_categories, search_places


SAMPLE_PLACE = PlaceRead(
    id=7,
    name="Museo Example",
    category="museum",
    description="Reviewed museum",
    address="Via Example 1",
    city="Torino",
    country_code="IT",
    latitude=45.07,
    longitude=7.68,
    price_level=None,
    rating=None,
    dietary_options=[],
    opening_hours=None,
    website="https://example.org",
    operator=None,
    primary_image=None,
)


class CityBuddyToolTests(unittest.TestCase):
    def test_categories_are_canonicalized_and_deduplicated(self):
        self.assertEqual(
            normalize_tool_categories(["Museum", "museum", "Cafe"]),
            ["museum", "cafe"],
        )

    def test_unknown_category_is_rejected_before_database_access(self):
        with self.assertRaisesRegex(ValueError, "Unsupported CityBuddy category"):
            normalize_tool_categories(["airport"])

    def test_location_arguments_must_be_supplied_together(self):
        with self.assertRaises(ValidationError):
            PlaceSearchInput(city="turin", latitude=45.07)

    def test_search_uses_controlled_retrieval_with_bounded_arguments(self):
        request = PlaceSearchInput(city="torino", categories=["Museum"], limit=3)
        database = object()
        with patch(
            "app.tools.citybuddy.retrieve_places",
            return_value=[RetrievedPlace(place=SAMPLE_PLACE, distance_km=None)],
        ) as retrieve:
            result = search_places(database, request)

        retrieve.assert_called_once_with(
            database,
            city="turin",
            categories=["museum"],
            limit=3,
            latitude=None,
            longitude=None,
            radius_km=None,
        )
        self.assertEqual(result.city, "Torino")
        self.assertEqual(result.count, 1)
        self.assertEqual(result.places[0].place.id, 7)

    def test_get_place_rejects_non_positive_ids_without_database_query(self):
        with patch("app.tools.citybuddy.retrieve_place_by_id") as retrieve:
            with self.assertRaisesRegex(ValueError, "positive CityBuddy place ID"):
                get_place(object(), place_id=0)
        retrieve.assert_not_called()

    def test_get_place_rejects_unknown_reviewed_id(self):
        with patch("app.tools.citybuddy.retrieve_place_by_id", return_value=None):
            with self.assertRaisesRegex(ValueError, "No reviewed CityBuddy place"):
                get_place(object(), place_id=999999)


if __name__ == "__main__":
    unittest.main()
