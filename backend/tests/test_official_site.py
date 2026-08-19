import unittest
from unittest.mock import patch

import httpx

from app.schemas.place import PlaceRead
from app.services.official_site import (
    OfficialSiteEvidence,
    fetch_official_site,
    validate_public_http_url,
)
from app.tools.official_site import get_official_place_page


SAMPLE_PLACE = PlaceRead(
    id=76,
    name="A come Ambiente",
    category="museum",
    description=None,
    address="Corso Umbria 90",
    city="Torino",
    country_code="IT",
    latitude=45.09,
    longitude=7.66,
    price_level=None,
    rating=None,
    dietary_options=[],
    opening_hours=None,
    website="https://example.org/",
    operator=None,
    primary_image=None,
)


def public_resolver(host: str, port: int) -> set[str]:
    return {"93.184.216.34"}


class OfficialSiteServiceTests(unittest.TestCase):
    def test_private_network_resolution_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-public network address"):
            validate_public_http_url(
                "http://localhost/",
                expected_official_host="localhost",
                resolver=lambda host, port: {"127.0.0.1"},
            )

    def test_redirect_to_different_domain_is_rejected_before_second_request(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(302, headers={"Location": "https://evil.example/menu"})

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ValueError, "reviewed official domain"):
                fetch_official_site(
                    place_id=76,
                    place_name="Museum",
                    website="https://example.org/",
                    page_type="menu",
                    client=client,
                    resolver=public_resolver,
                )

        self.assertEqual(requested, ["https://example.org/"])

    def test_menu_page_follows_only_same_domain_matching_link(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text=(
                        "<html><head><title>Official Museum</title></head><body>"
                        "<a href='https://outside.example/menu'>External menu</a>"
                        "<a href='/menu'>Food menu</a>"
                        "</body></html>"
                    ),
                )
            self.assertEqual(request.url.path, "/menu")
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text=(
                    "<html><head><title>Cafe menu</title><style>hidden</style></head>"
                    "<body><script>ignore me</script><h1>Lunch menu</h1>Soup and pasta</body></html>"
                ),
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=76,
                place_name="Museum",
                website="https://example.org/",
                page_type="menu",
                client=client,
                resolver=public_resolver,
            )

        self.assertEqual(requested, ["https://example.org/", "https://example.org/menu"])
        self.assertEqual(result.source_url, "https://example.org/menu")
        self.assertEqual(result.official_host, "example.org")
        self.assertEqual(result.title, "Cafe menu")
        self.assertIn("Lunch menu", result.text)
        self.assertIn("Soup and pasta", result.text)
        self.assertNotIn("ignore me", result.text)
        self.assertNotIn("hidden", result.text)


    def test_general_query_can_follow_matching_same_domain_link(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text=(
                        "<html><body>"
                        "<a href='/brands'>Brands and collections</a>"
                        "<a href='https://outside.example/collections'>External collections</a>"
                        "</body></html>"
                    ),
                )
            self.assertEqual(request.url.path, "/brands")
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><body>Men Women Kids fashion collections</body></html>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=76,
                place_name="Mall",
                website="https://example.org/",
                page_type="general",
                query="What men's, women's and kids collections are there?",
                client=client,
                resolver=public_resolver,
            )

        self.assertEqual(requested, ["https://example.org/", "https://example.org/brands"])
        self.assertEqual(result.source_url, "https://example.org/brands")
        self.assertIn("Men Women Kids", result.text)

    def test_no_readable_static_content_returns_safe_unverified_evidence(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><body><script>window.app = {}</script><style>body{}</style></body></html>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=76,
                place_name="Museum",
                website="https://example.org/",
                page_type="general",
                client=client,
                resolver=public_resolver,
            )

        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "no_readable_static_content")
        self.assertEqual(result.source_url, "https://example.org/")
        self.assertEqual(result.official_host, "example.org")
        self.assertIsNone(result.text)

    def test_unsupported_content_type_is_rejected(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"Content-Type": "application/pdf"},
                content=b"not really a pdf",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaisesRegex(ValueError, "unsupported content type"):
                fetch_official_site(
                    place_id=76,
                    place_name="Museum",
                    website="https://example.org/",
                    page_type="general",
                    client=client,
                    resolver=public_resolver,
                )


class OfficialSiteToolTests(unittest.TestCase):
    def test_tool_requires_reviewed_place_with_stored_website(self):
        no_site = SAMPLE_PLACE.model_copy(update={"website": None})
        with patch("app.tools.official_site.retrieve_place_by_id", return_value=no_site):
            with self.assertRaisesRegex(ValueError, "no official website stored"):
                get_official_place_page(object(), place_id=76, page_type="general")

    def test_tool_uses_only_stored_reviewed_website(self):
        evidence = OfficialSiteEvidence(
            place_id=76,
            place_name="A come Ambiente",
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
        with (
            patch("app.tools.official_site.retrieve_place_by_id", return_value=SAMPLE_PLACE),
            patch("app.tools.official_site.fetch_official_site", return_value=evidence) as fetch,
        ):
            result = get_official_place_page(object(), place_id=76, page_type="general")

        fetch.assert_called_once_with(
            place_id=76,
            place_name="A come Ambiente",
            website="https://example.org/",
            page_type="general",
            query=None,
        )
        self.assertEqual(result.source_url, "https://example.org/")


if __name__ == "__main__":
    unittest.main()
