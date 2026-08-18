from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.cities import CityConfig, get_city
from app.services.weather import MetNorwayWeatherProvider, WeatherForecast, WeatherProvider


class WeatherRequest(BaseModel):
    """Validated CityBuddy weather request."""

    model_config = ConfigDict(extra="forbid")

    city: str = Field(min_length=1, max_length=100)
    forecast_hours: int = Field(default=12, ge=1, le=48)
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)

    @model_validator(mode="after")
    def validate_location_pair(self) -> "WeatherRequest":
        supplied = (self.latitude is not None, self.longitude is not None)
        if supplied.count(True) == 1:
            raise ValueError("latitude and longitude must be supplied together")
        return self


def _city_center(city: CityConfig) -> tuple[float, float]:
    return city.center


def _validate_coordinates_for_city(
    city: CityConfig,
    *,
    latitude: float,
    longitude: float,
) -> None:
    south, west, north, east = city.bounding_box
    if not (south <= latitude <= north and west <= longitude <= east):
        raise ValueError(
            f"Coordinates must be inside the supported {city.display_name} city bounds."
        )


def get_weather(
    request: WeatherRequest,
    *,
    provider: WeatherProvider | None = None,
) -> WeatherForecast:
    """Retrieve bounded weather for a supported CityBuddy city."""

    city = get_city(request.city)
    if request.latitude is None or request.longitude is None:
        latitude, longitude = _city_center(city)
    else:
        latitude, longitude = request.latitude, request.longitude
        _validate_coordinates_for_city(
            city,
            latitude=latitude,
            longitude=longitude,
        )

    selected_provider = provider or MetNorwayWeatherProvider()
    return selected_provider.get_forecast(
        city=city.display_name,
        latitude=latitude,
        longitude=longitude,
        timezone_name=city.timezone,
        forecast_hours=request.forecast_hours,
    )
