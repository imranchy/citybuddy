import asyncio
import unittest
from unittest.mock import patch

from mcp import Client

from app.mcp.server import mcp
from app.services.official_site import OfficialSiteEvidence
from app.services.weather import WeatherForecast, WeatherPoint
from app.tools.citybuddy import PlaceSearchResult



class MCPServerTests(unittest.TestCase):
    def test_server_exposes_only_allowlisted_citybuddy_tools(self):
        async def run_test():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return {tool.name for tool in tools.tools}

        names = asyncio.run(run_test())
        self.assertEqual(
            names,
            {
                "search_citybuddy_places",
                "get_place_details",
                "get_official_place_page",
                "get_weather",
            },
        )
        forbidden_fragments = {"sql", "shell", "filesystem", "url", "write", "fetch"}
        for name in names:
            self.assertTrue(forbidden_fragments.isdisjoint(name.lower().split("_")))

    def test_mcp_search_returns_structured_content(self):
        fake = PlaceSearchResult(city="Torino", categories=["museum"], count=0, places=[])

        async def run_test():
            with patch("app.mcp.server.search_places", return_value=fake):
                async with Client(mcp) as client:
                    return await client.call_tool(
                        "search_citybuddy_places",
                        {"city": "turin", "categories": ["museum"], "limit": 2},
                    )

        result = asyncio.run(run_test())
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["city"], "Torino")
        self.assertEqual(result.structured_content["count"], 0)

    def test_mcp_rejects_out_of_bounds_limit_before_tool_body(self):
        async def run_test():
            with patch("app.mcp.server.search_places") as search:
                async with Client(mcp) as client:
                    result = await client.call_tool(
                        "search_citybuddy_places",
                        {"city": "turin", "limit": 500},
                    )
                    return result, search.called

        result, called = asyncio.run(run_test())
        self.assertTrue(result.is_error)
        self.assertFalse(called)

    def test_official_site_tool_has_no_caller_supplied_url_argument(self):
        async def run_test():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return next(tool for tool in tools.tools if tool.name == "get_official_place_page")

        tool = asyncio.run(run_test())
        properties = tool.input_schema.get("properties", {})
        self.assertEqual(set(properties), {"place_id", "page_type", "query"})
        self.assertNotIn("url", properties)

    def test_mcp_official_site_returns_structured_content(self):
        fake = OfficialSiteEvidence(
            place_id=76,
            place_name="Museum",
            page_type="general",
            official_host="example.org",
            source_url="https://example.org/",
            fetched_at="2026-08-18T14:00:00Z",
            verified=True,
            reason=None,
            title="Museum",
            text="Official information",
            truncated=False,
        )

        async def run_test():
            with patch("app.mcp.server.retrieve_official_place_page", return_value=fake):
                async with Client(mcp) as client:
                    return await client.call_tool(
                        "get_official_place_page",
                        {
                            "place_id": 76,
                            "page_type": "general",
                            "query": "What facilities are available?",
                        },
                    )

        result = asyncio.run(run_test())
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["place_id"], 76)
        self.assertEqual(result.structured_content["source_url"], "https://example.org/")
        self.assertTrue(result.structured_content["verified"])
        self.assertIsNone(result.structured_content["reason"])


    def test_weather_tool_has_no_caller_supplied_url_argument(self):
        async def run_test():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return next(tool for tool in tools.tools if tool.name == "get_weather")

        tool = asyncio.run(run_test())
        properties = tool.input_schema.get("properties", {})
        self.assertEqual(
            set(properties),
            {"city", "forecast_hours", "latitude", "longitude"},
        )
        self.assertNotIn("url", properties)
        self.assertNotIn("provider", properties)

    def test_mcp_weather_returns_structured_content(self):
        point = WeatherPoint(
            time="2026-08-18T14:00:00Z",
            air_temperature_c=22.5,
            relative_humidity_percent=55.0,
            wind_speed_mps=2.4,
            precipitation_amount_mm=0.0,
            symbol_code="clearsky_day",
        )
        fake = WeatherForecast(
            city="Torino",
            latitude=45.0703,
            longitude=7.6869,
            timezone="Europe/Rome",
            forecast_hours=12,
            fetched_at="2026-08-18T14:00:00Z",
            source_updated_at="2026-08-18T13:55:00Z",
            source="MET Norway Locationforecast",
            attribution="Data from MET Norway",
            license="NLOD 2.0 / CC BY 4.0",
            current=point,
            forecast=[],
        )

        async def run_test():
            with patch("app.mcp.server.retrieve_weather", return_value=fake):
                async with Client(mcp) as client:
                    return await client.call_tool(
                        "get_weather",
                        {"city": "turin", "forecast_hours": 12},
                    )

        result = asyncio.run(run_test())
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["city"], "Torino")
        self.assertEqual(result.structured_content["current"]["air_temperature_c"], 22.5)
        self.assertEqual(result.structured_content["source"], "MET Norway Locationforecast")


if __name__ == "__main__":
    unittest.main()
