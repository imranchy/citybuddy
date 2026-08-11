from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.core.place_catalog import DESTINATION_CATEGORIES
from app.core.cities import get_city
from app.models.place import Place
from app.models.place_image import PlaceImage
from app.schemas.place import PlaceRead
from app.services.place_types import RetrievedPlace


def _primary_image_expression():
    return (
        select(
            func.json_build_object(
                "source",
                PlaceImage.source,
                "image_url",
                PlaceImage.image_url,
                "thumbnail_url",
                PlaceImage.thumbnail_url,
                "source_page_url",
                PlaceImage.source_page_url,
                "attribution",
                PlaceImage.attribution,
                "license",
                PlaceImage.license,
                "license_url",
                PlaceImage.license_url,
            )
        )
        .where(PlaceImage.place_id == Place.id)
        .order_by(PlaceImage.is_primary.desc(), PlaceImage.id)
        .limit(1)
        .scalar_subquery()
        .label("primary_image")
    )


def _place_columns():
    return (
        Place.id,
        Place.name,
        Place.category,
        Place.description,
        Place.address,
        Place.city,
        Place.country_code,
        func.ST_Y(cast(Place.location, Geometry(srid=4326))).label("latitude"),
        func.ST_X(cast(Place.location, Geometry(srid=4326))).label("longitude"),
        Place.price_level,
        Place.rating,
        Place.dietary_options,
        Place.opening_hours,
        Place.website,
        Place.operator,
        _primary_image_expression(),
    )


def retrieve_places(
    database: Session,
    *,
    city: str,
    categories: list[str],
    limit: int,
    latitude: float | None = None,
    longitude: float | None = None,
    radius_km: float | None = None,
    place_ids: list[int] | None = None,
) -> list[RetrievedPlace]:
    """Retrieve reviewed places through controlled SQLAlchemy filters."""

    distance_expression = None
    city_name = get_city(city).display_name
    statement = select(*_place_columns()).where(
        Place.category.in_(DESTINATION_CATEGORIES),
        func.lower(Place.city) == city_name.casefold(),
    )

    if categories:
        statement = statement.where(Place.category.in_(categories))
    if place_ids:
        statement = statement.where(Place.id.in_(place_ids))

    if latitude is not None and longitude is not None:
        user_location = cast(
            func.ST_SetSRID(func.ST_MakePoint(longitude, latitude), 4326),
            Geography(geometry_type="POINT", srid=4326),
        )
        distance_expression = (
            func.ST_Distance(Place.location, user_location) / 1000.0
        ).label("distance_km")
        statement = statement.add_columns(distance_expression).where(
            func.ST_DWithin(
                Place.location,
                user_location,
                (radius_km or 2.0) * 1000,
            )
        )

    statement = statement.order_by(
        distance_expression if distance_expression is not None else Place.name
    ).limit(min(max(limit, 1), 10))

    rows = database.execute(statement).mappings().all()
    return [
        RetrievedPlace(
            place=PlaceRead.model_validate(
                {key: value for key, value in dict(row).items() if key != "distance_km"}
            ),
            distance_km=(
                float(row["distance_km"])
                if row.get("distance_km") is not None
                else None
            ),
        )
        for row in rows
    ]
