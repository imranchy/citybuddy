from datetime import datetime
import unittest
from unittest.mock import Mock

import httpx
from pydantic import ValidationError

from app.services.weather import MET_NO_USER_AGENT, MetNorwayWeatherProvider, WeatherForecast
from app.tools.weather import WeatherRequest, get_weather


class WeatherToolTests(unittest.TestCase):
    def test_coordinates_must_be_supplied_together(self):
        with self.assertRaises(ValidationError):
            WeatherRequest(city="turin", latitude=45.07)

    def test_coordinates_must_stay_inside_supported_city(self):
        request = WeatherRequest(
            city="turin",
            latitude=41.9028,
            longitude=12.4964,
        )
        with self.assertRaisesRegex(ValueError, "inside the supported Torino city bounds"):
            get_weather(request, provider=Mock())

    def test_city_center_is_used_when_coordinates_are_omitted(self):
        provider = Mock()
        provider.get_forecast.return_value = _fake_forecast()

        result = get_weather(
            WeatherRequest(city="torino", forecast_hours=6),
            provider=provider,
        )

        self.assertEqual(result.city, "Torino")
        kwargs = provider.get_forecast.call_args.kwargs
        self.assertAlmostEqual(kwargs["latitude"], 45.0703)
        self.assertAlmostEqual(kwargs["longitude"], 7.6869)
        self.assertEqual(kwargs["forecast_hours"], 6)
        self.assertEqual(kwargs["timezone_name"], "Europe/Rome")


class MetNorwayWeatherProviderTests(unittest.TestCase):
    def test_provider_sends_identifying_user_agent_and_rounds_coordinates(self):
        seen_request = None

        def handler(request: httpx.Request) -> httpx.Response:
            nonlocal seen_request
            seen_request = request
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json=_met_payload(),
            )

        client = httpx.Client(transport=httpx.MockTransport(handler))
        provider = MetNorwayWeatherProvider(client=client)
        provider.get_forecast(
            city="Torino",
            latitude=45.07031234,
            longitude=7.68691234,
            timezone_name="Europe/Rome",
            forecast_hours=2,
        )

        self.assertIsNotNone(seen_request)
        assert seen_request is not None
        self.assertEqual(seen_request.headers["user-agent"], MET_NO_USER_AGENT)
        self.assertEqual(seen_request.url.params["lat"], "45.0703")
        self.assertEqual(seen_request.url.params["lon"], "7.6869")

    def test_provider_parses_current_conditions_and_bounded_forecast(self):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "application/json"},
                    json=_met_payload(),
                )
            )
        )
        result = MetNorwayWeatherProvider(client=client).get_forecast(
            city="Torino",
            latitude=45.0703,
            longitude=7.6869,
            timezone_name="Europe/Rome",
            forecast_hours=2,
        )

        self.assertEqual(result.city, "Torino")
        self.assertEqual(result.forecast_hours, 2)
        self.assertEqual(result.current.air_temperature_c, 22.5)
        self.assertEqual(result.current.relative_humidity_percent, 55.0)
        self.assertEqual(result.current.wind_speed_mps, 2.4)
        self.assertEqual(result.current.precipitation_amount_mm, 0.0)
        self.assertEqual(result.current.symbol_code, "clearsky_day")
        self.assertEqual(len(result.forecast), 2)
        self.assertEqual(result.forecast[-1].air_temperature_c, 24.0)
        self.assertEqual(result.source, "MET Norway Locationforecast")
        self.assertIn("MET Norway", result.attribution)
        self.assertIsInstance(result.source_updated_at, datetime)

    def test_provider_rejects_non_json_response(self):
        client = httpx.Client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(
                    200,
                    headers={"content-type": "text/html"},
                    text="not weather json",
                )
            )
        )
        with self.assertRaisesRegex(ValueError, "unsupported content type"):
            MetNorwayWeatherProvider(client=client).get_forecast(
                city="Torino",
                latitude=45.07,
                longitude=7.68,
                timezone_name="Europe/Rome",
                forecast_hours=2,
            )


def _fake_forecast() -> WeatherForecast:
    client = httpx.Client(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json=_met_payload(),
            )
        )
    )
    return MetNorwayWeatherProvider(client=client).get_forecast(
        city="Torino",
        latitude=45.0703,
        longitude=7.6869,
        timezone_name="Europe/Rome",
        forecast_hours=2,
    )


def _met_payload() -> dict:
    return {
        "properties": {
            "meta": {"updated_at": "2026-08-18T14:00:00Z"},
            "timeseries": [
                _series("2026-08-18T14:00:00Z", 22.5, 55, 2.4, 0.0, "clearsky_day"),
                _series("2026-08-18T15:00:00Z", 23.2, 52, 2.7, 0.0, "fair_day"),
                _series("2026-08-18T16:00:00Z", 24.0, 50, 3.0, 0.1, "partlycloudy_day"),
                _series("2026-08-18T17:00:00Z", 23.6, 53, 2.8, 0.4, "lightrain"),
            ],
        }
    }


def _series(
    time: str,
    temperature: float,
    humidity: float,
    wind_speed: float,
    precipitation: float,
    symbol: str,
) -> dict:
    return {
        "time": time,
        "data": {
            "instant": {
                "details": {
                    "air_temperature": temperature,
                    "relative_humidity": humidity,
                    "wind_speed": wind_speed,
                }
            },
            "next_1_hours": {
                "summary": {"symbol_code": symbol},
                "details": {"precipitation_amount": precipitation},
            },
        },
    }


if __name__ == "__main__":
    unittest.main()
