from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.place import Place


SEED_PLACES = [
    {
        "name": "Chiodi Latini New Food",
        "category": "restaurant",
        "description": "Plant-based restaurant offering vegan and vegetarian cuisine.",
        "address": "Via San Quintino 33/C",
        "city": "Torino",
        "country_code": "IT",
        "latitude": 45.0670155,
        "longitude": 7.6703269,
        "price_level": None,
        "rating": None,
        "dietary_options": ["vegetarian", "vegan"],
    },
    {
        "name": "Kirkuk Kaffé",
        "category": "restaurant",
        "description": "Middle Eastern and Kurdish restaurant offering vegetarian dishes.",
        "address": "Via Carlo Alberto 16",
        "city": "Torino",
        "country_code": "IT",
        "latitude": 45.066933,
        "longitude": 7.6849108,
        "price_level": None,
        "rating": None,
        "dietary_options": ["vegetarian"],
    },
]


def seed_places() -> None:
    with SessionLocal() as database:
        existing_names = set(
            database.scalars(
                select(Place.name).where(Place.city == "Torino")
            ).all()
        )

        new_places = []

        for place_data in SEED_PLACES:
            if place_data["name"] in existing_names:
                continue

            latitude = place_data.pop("latitude")
            longitude = place_data.pop("longitude")

            place = Place(
                **place_data,
                location=WKTElement(
                    f"POINT({longitude} {latitude})",
                    srid=4326,
                ),
            )
            new_places.append(place)

        database.add_all(new_places)
        database.commit()

        print(f"Inserted {len(new_places)} places.")


if __name__ == "__main__":
    seed_places()