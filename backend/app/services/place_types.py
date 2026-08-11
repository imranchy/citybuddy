from dataclasses import dataclass

from app.schemas.place import PlaceRead


@dataclass(frozen=True, slots=True)
class RetrievedPlace:
    place: PlaceRead
    distance_km: float | None = None
