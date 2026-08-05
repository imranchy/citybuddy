from typing import Annotated

from fastapi import APIRouter, Depends, Query
from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.place import Place
from app.schemas.place import NearbyPlaceRead, PlaceRead

from app.models.place_image import PlaceImage

router = APIRouter(
    prefix="/api/places",
    tags=["places"],
)

def primary_image_expression():
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
        .order_by(
            PlaceImage.is_primary.desc(),
            PlaceImage.id,
        )
        .limit(1)
        .scalar_subquery()
        .label("primary_image")
    )

@router.get("", response_model=list[PlaceRead])
def list_places(
    database: Annotated[Session, Depends(get_db)],
    category: str | None = None,
    city: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[PlaceRead]:
    statement = select(
        Place.id,
        Place.name,
        Place.category,
        Place.description,
        Place.address,
        Place.city,
        Place.country_code,
        func.ST_Y(
            cast(Place.location, Geometry(srid=4326))
        ).label("latitude"),
        func.ST_X(
            cast(Place.location, Geometry(srid=4326))
        ).label("longitude"),
        Place.price_level,
        Place.rating,
        Place.dietary_options,
        primary_image_expression(),
    )

    if category:
        statement = statement.where(
            func.lower(Place.category) == category.lower()
        )

    if city:
        statement = statement.where(
            func.lower(Place.city) == city.lower()
        )

    statement = (
        statement
        .order_by(Place.name)
        .offset(offset)
        .limit(limit)
    )

    places = database.execute(statement).mappings().all()

    return [
        PlaceRead.model_validate(dict(place))
        for place in places
    ]

@router.get(
    "/categories",
    response_model=list[str],
)
def list_place_categories(
    database: Annotated[Session, Depends(get_db)],
) -> list[str]:
    statement = (
        select(Place.category)
        .where(Place.category.is_not(None))
        .distinct()
        .order_by(Place.category)
    )

    categories = database.scalars(statement).all()

    return list(categories)

@router.get(
    "/nearby",
    response_model=list[NearbyPlaceRead],
)
def list_nearby_places(
    database: Annotated[Session, Depends(get_db)],
    latitude: Annotated[
        float,
        Query(ge=-90, le=90),
    ],
    longitude: Annotated[
        float,
        Query(ge=-180, le=180),
    ],
    radius_km: Annotated[
        float,
        Query(gt=0, le=50),
    ] = 2.0,
    category: str | None = None,
    limit: Annotated[
        int,
        Query(ge=1, le=200),
    ] = 50,
) -> list[NearbyPlaceRead]:
    user_location = cast(
        func.ST_SetSRID(
            func.ST_MakePoint(longitude, latitude),
            4326,
        ),
        Geography(
            geometry_type="POINT",
            srid=4326,
        ),
    )

    distance_km = (
        func.ST_Distance(
            Place.location,
            user_location,
        )
        / 1000.0
    ).label("distance_km")

    statement = (
        select(
            Place.id,
            Place.name,
            Place.category,
            Place.description,
            Place.address,
            Place.city,
            Place.country_code,
            func.ST_Y(
                cast(Place.location, Geometry(srid=4326))
            ).label("latitude"),
            func.ST_X(
                cast(Place.location, Geometry(srid=4326))
            ).label("longitude"),
            Place.price_level,
            Place.rating,
            Place.dietary_options,
            primary_image_expression(),
            distance_km,
        )
        .where(
            func.ST_DWithin(
                Place.location,
                user_location,
                radius_km * 1000,
            )
        )
    )

    if category:
        statement = statement.where(
            func.lower(Place.category) == category.lower()
        )

    statement = (
        statement
        .order_by(distance_km)
        .limit(limit)
    )

    places = database.execute(statement).mappings().all()

    return [
        NearbyPlaceRead.model_validate(dict(place))
        for place in places
    ]