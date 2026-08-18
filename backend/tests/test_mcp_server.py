import asyncio
import unittest
from unittest.mock import patch

from mcp import Client

from app.mcp.server import mcp
from app.tools.citybuddy import PlaceSearchResult



class MCPServerTests(unittest.TestCase):
    def test_server_exposes_only_allowlisted_citybuddy_tools(self):
        async def run_test():
            async with Client(mcp) as client:
                tools = await client.list_tools()
                return {tool.name for tool in tools.tools}

        names = asyncio.run(run_test())
        self.assertEqual(names, {"search_citybuddy_places", "get_place_details"})
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


if __name__ == "__main__":
    unittest.main()
