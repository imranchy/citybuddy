from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CityConfig:
    """Configuration required to ingest and present a supported city."""

    key: str
    display_name: str
    country_code: str
    bounding_box: tuple[float, float, float, float]
    default_language: str
    supported_languages: tuple[str, ...]
    timezone: str

    @property
    def overpass_bounding_box(self) -> str:
        return ",".join(str(value) for value in self.bounding_box)


CITIES: dict[str, CityConfig] = {
    "turin": CityConfig(
        key="turin",
        display_name="Torino",
        country_code="IT",
        # South, west, north and east boundaries covering Turin.
        bounding_box=(44.9580, 7.5770, 45.1330, 7.7730),
        default_language="it",
        supported_languages=("it", "en"),
        timezone="Europe/Rome",
    ),
}

CITY_ALIASES = {
    "torino": "turin",
}


def get_city(city_key: str) -> CityConfig:
    """Return a supported city configuration by key or known alias."""

    normalized_key = city_key.strip().lower()
    normalized_key = CITY_ALIASES.get(normalized_key, normalized_key)

    try:
        return CITIES[normalized_key]
    except KeyError as error:
        available_cities = ", ".join(sorted(CITIES))
        raise ValueError(
            f"Unsupported city '{city_key}'. Available cities: "
            f"{available_cities}."
        ) from error
