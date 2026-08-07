from typing import Annotated

from fastapi import APIRouter, Depends, Query
from geoalchemy2 import Geography, Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.api.routes.places import primary_image_expression
from app.core.place_catalog import TRANSPORT_CATEGORIES
from app.db.database import get_db
from app.models.place import Place
from app.schemas.place import NearbyPlaceRead, PlaceRead


router = APIRouter(
    prefix="/api/transport",
    tags=["transport"],
)


@router.get("", response_model=list[PlaceRead])
def list_transport_places(
    database: Annotated[Session, Depends(get_db)],
    category: str | None = None,
    city: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
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
        Place.opening_hours,
        Place.website,
        Place.operator,
        primary_image_expression(),
    ).where(Place.category.in_(TRANSPORT_CATEGORIES))

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
def list_transport_categories(
    database: Annotated[Session, Depends(get_db)],
) -> list[str]:
    statement = (
        select(Place.category)
        .where(Place.category.in_(TRANSPORT_CATEGORIES))
        .distinct()
        .order_by(Place.category)
    )

    categories = database.scalars(statement).all()

    return list(categories)


@router.get(
    "/nearby",
    response_model=list[NearbyPlaceRead],
)
def list_nearby_transport(
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
    ] = 100,
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
            Place.opening_hours,
            Place.website,
            Place.operator,
            primary_image_expression(),
            distance_km,
        )
        .where(
            func.ST_DWithin(
                Place.location,
                user_location,
                radius_km * 1000,
            ),
            Place.category.in_(TRANSPORT_CATEGORIES),
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