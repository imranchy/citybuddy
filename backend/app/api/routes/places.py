from typing import Annotated

from fastapi import APIRouter, Depends
from geoalchemy2 import Geometry
from sqlalchemy import cast, func, select
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.place import Place
from app.schemas.place import PlaceRead


router = APIRouter(
    prefix="/api/places",
    tags=["places"],
)


@router.get("", response_model=list[PlaceRead])
def list_places(
    database: Annotated[Session, Depends(get_db)],
) -> list[PlaceRead]:
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
        )
        .order_by(Place.name)
    )

    places = database.execute(statement).mappings().all()

    return [
        PlaceRead.model_validate(dict(place))
        for place in places
    ]