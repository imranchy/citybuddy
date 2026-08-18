from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

import httpx
from pydantic import BaseModel, ConfigDict


MET_NO_ENDPOINT = "https://api.met.no/weatherapi/locationforecast/2.0/compact"
MET_NO_USER_AGENT = "CityBuddy/0.1 https://github.com/imranchy/citybuddy"
MET_NO_ATTRIBUTION = "Data from MET Norway"
MET_NO_LICENSE = "NLOD 2.0 / CC BY 4.0"
REQUEST_TIMEOUT = httpx.Timeout(8.0, connect=5.0)
MAX_RESPONSE_BYTES = 1_000_000


class WeatherPoint(BaseModel):
    """One timestamped weather observation/forecast point."""

    model_config = ConfigDict(extra="forbid")

    time: datetime
    air_temperature_c: float
    relative_humidity_percent: float | None
    wind_speed_mps: float | None
    precipitation_amount_mm: float | None
    symbol_code: str | None


class WeatherForecast(BaseModel):
    """Bounded weather evidence returned to CityBuddy."""

    model_config = ConfigDict(extra="forbid")

    city: str
    latitude: float
    longitude: float
    timezone: str
    forecast_hours: int
    fetched_at: datetime
    source_updated_at: datetime | None
    source: str
    attribution: str
    license: str
    current: WeatherPoint
    forecast: list[WeatherPoint]


class WeatherProvider(Protocol):
    """Swappable weather provider boundary used by CityBuddy."""

    def get_forecast(
        self,
        *,
        city: str,
        latitude: float,
        longitude: float,
        timezone_name: str,
        forecast_hours: int,
    ) -> WeatherForecast: ...


class MetNorwayWeatherProvider:
    """Keyless MET Norway Locationforecast provider."""

    def __init__(self, *, client: httpx.Client | None = None) -> None:
        self._client = client

    def get_forecast(
        self,
        *,
        city: str,
        latitude: float,
        longitude: float,
        timezone_name: str,
        forecast_hours: int,
    ) -> WeatherForecast:
        if not 1 <= forecast_hours <= 48:
            raise ValueError("forecast_hours must be between 1 and 48")

        params = {
            # MET Norway asks clients not to use more than four decimals so
            # forecasts can be cached effectively.
            "lat": f"{latitude:.4f}",
            "lon": f"{longitude:.4f}",
        }
        headers = {
            "User-Agent": MET_NO_USER_AGENT,
            "Accept": "application/json",
        }

        if self._client is not None:
            payload = self._request_payload(self._client, params=params, headers=headers)
        else:
            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                payload = self._request_payload(client, params=params, headers=headers)

        return self._parse_payload(
            payload,
            city=city,
            latitude=latitude,
            longitude=longitude,
            timezone_name=timezone_name,
            forecast_hours=forecast_hours,
        )

    @staticmethod
    def _request_payload(
        client: httpx.Client,
        *,
        params: dict[str, str],
        headers: dict[str, str],
    ) -> dict:
        try:
            response = client.get(
                MET_NO_ENDPOINT,
                params=params,
                headers=headers,
                timeout=REQUEST_TIMEOUT,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ValueError("Weather provider request timed out.") from exc
        except httpx.HTTPStatusError as exc:
            raise ValueError(
                f"Weather provider returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise ValueError("Weather provider request failed.") from exc

        content_type = response.headers.get("content-type", "").casefold()
        if "application/json" not in content_type:
            raise ValueError("Weather provider returned an unsupported content type.")
        if len(response.content) > MAX_RESPONSE_BYTES:
            raise ValueError("Weather provider response exceeded CityBuddy's safety limit.")

        try:
            payload = response.json()
        except ValueError as exc:
            raise ValueError("Weather provider returned invalid JSON.") from exc
        if not isinstance(payload, dict):
            raise ValueError("Weather provider returned an invalid response shape.")
        return payload

    @staticmethod
    def _parse_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

    @classmethod
    def _point_from_timeseries(cls, item: dict) -> WeatherPoint:
        try:
            timestamp = cls._parse_time(item["time"])
            data = item["data"]
            instant = data["instant"]["details"]
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Weather provider response is missing required forecast fields.") from exc

        next_hour = data.get("next_1_hours") or {}
        next_hour_details = next_hour.get("details") or {}
        next_hour_summary = next_hour.get("summary") or {}

        try:
            temperature = float(instant["air_temperature"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Weather provider response is missing air temperature.") from exc

        def optional_float(container: dict, key: str) -> float | None:
            value = container.get(key)
            if value is None:
                return None
            try:
                return float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Weather provider returned an invalid numeric value for {key}."
                ) from exc

        symbol_code = next_hour_summary.get("symbol_code")
        if symbol_code is not None and not isinstance(symbol_code, str):
            raise ValueError("Weather provider returned an invalid weather symbol.")

        return WeatherPoint(
            time=timestamp,
            air_temperature_c=temperature,
            relative_humidity_percent=optional_float(instant, "relative_humidity"),
            wind_speed_mps=optional_float(instant, "wind_speed"),
            precipitation_amount_mm=optional_float(
                next_hour_details,
                "precipitation_amount",
            ),
            symbol_code=symbol_code,
        )

    @classmethod
    def _parse_payload(
        cls,
        payload: dict,
        *,
        city: str,
        latitude: float,
        longitude: float,
        timezone_name: str,
        forecast_hours: int,
    ) -> WeatherForecast:
        try:
            properties = payload["properties"]
            timeseries = properties["timeseries"]
        except (KeyError, TypeError) as exc:
            raise ValueError("Weather provider response is missing forecast data.") from exc

        if not isinstance(timeseries, list) or not timeseries:
            raise ValueError("Weather provider returned no forecast points.")

        current = cls._point_from_timeseries(timeseries[0])
        forecast_end = current.time + timedelta(hours=forecast_hours)
        forecast: list[WeatherPoint] = []

        for item in timeseries[1:]:
            point = cls._point_from_timeseries(item)
            if point.time > forecast_end:
                break
            if point.time > current.time:
                forecast.append(point)

        meta = properties.get("meta") or {}
        updated_value = meta.get("updated_at")
        source_updated_at = None
        if updated_value is not None:
            if not isinstance(updated_value, str):
                raise ValueError("Weather provider returned an invalid update timestamp.")
            try:
                source_updated_at = cls._parse_time(updated_value)
            except ValueError as exc:
                raise ValueError("Weather provider returned an invalid update timestamp.") from exc

        return WeatherForecast(
            city=city,
            latitude=round(latitude, 4),
            longitude=round(longitude, 4),
            timezone=timezone_name,
            forecast_hours=forecast_hours,
            fetched_at=datetime.now(timezone.utc),
            source_updated_at=source_updated_at,
            source="MET Norway Locationforecast",
            attribution=MET_NO_ATTRIBUTION,
            license=MET_NO_LICENSE,
            current=current,
            forecast=forecast,
        )
