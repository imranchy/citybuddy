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
    def test_requests_send_browser_compatible_content_headers(self):
        observed: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            observed["user_agent"] = request.headers.get("user-agent", "")
            observed["accept"] = request.headers.get("accept", "")
            observed["accept_language"] = request.headers.get("accept-language", "")
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><body>Official information</body></html>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=76,
                place_name="Cafe",
                website="https://example.org/",
                page_type="general",
                client=client,
                resolver=public_resolver,
            )

        self.assertTrue(result.verified)
        self.assertIn("Mozilla/5.0", observed["user_agent"])
        self.assertIn("CityBuddy/0.1", observed["user_agent"])
        self.assertIn("text/html", observed["accept"])
        self.assertIn("application/xhtml+xml", observed["accept"])
        self.assertIn("it-IT", observed["accept_language"])

    def test_static_retrieval_block_returns_safe_unverified_evidence(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(406, headers={"Content-Type": "text/html"}, text="blocked")

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=1015,
                place_name="Avocuddle cafe",
                website="https://example.org/",
                page_type="general",
                query="menu vegetarian vegan dietary",
                client=client,
                resolver=public_resolver,
            )

        self.assertFalse(result.verified)
        self.assertEqual(result.reason, "static_retrieval_blocked")
        self.assertIsNone(result.text)

    def test_query_one_hop_supports_all_current_document_topic_aliases(self):
        cases = (
            ("accessibility wheelchair disabled barrier accessible", "/accessibilita/", "Accessibilità sedia a rotelle"),
            ("visitor services facilities amenities parking family children info toilets", "/info/", "Servizi parcheggio toilettes famiglie"),
            ("permanent collections collection visitor highlights works masterpieces", "/collezioni/", "Collezioni permanenti opere e capolavori"),
            ("shops stores brands directory men women kids collections botteghe artigiani", "/botteghe/", "Botteghe artigiani negozi e marchi"),
            ("dietary vegetarian vegan gluten allergens halal food policy menu intolleranze", "/menu/", "Menu vegetariano vegano allergeni e intolleranze"),
        )

        for query, path, body in cases:
            with self.subTest(path=path):
                requested: list[str] = []

                def handler(request: httpx.Request) -> httpx.Response:
                    requested.append(str(request.url))
                    if request.url.path == "/":
                        anchor = path.strip("/").replace("-", " ")
                        return httpx.Response(
                            200,
                            headers={"Content-Type": "text/html"},
                            text=f"<html><body><a href='{path}'>{anchor}</a></body></html>",
                        )
                    return httpx.Response(
                        200,
                        headers={"Content-Type": "text/html"},
                        text=f"<html><body>{body}</body></html>",
                    )

                with httpx.Client(transport=httpx.MockTransport(handler)) as client:
                    result = fetch_official_site(
                        place_id=1,
                        place_name="Example",
                        website="https://example.org/",
                        page_type="general",
                        query=query,
                        client=client,
                        resolver=public_resolver,
                    )

                self.assertTrue(result.verified)
                self.assertEqual(result.source_url, f"https://example.org{path}")
                self.assertIn(body.split()[0], result.text or "")
                self.assertLessEqual(len(requested), 1 + 3)

    def test_query_one_hop_can_skip_weak_candidate_for_stronger_page(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text=(
                        "<html><body>"
                        "<a href='/shop/'>Shop</a>"
                        "<a href='/botteghe/'>Le botteghe degli artigiani</a>"
                        "</body></html>"
                    ),
                )
            if request.url.path == "/shop/":
                return httpx.Response(
                    200, headers={"Content-Type": "text/html"},
                    text="<html><body>Gift shop</body></html>",
                )
            return httpx.Response(
                200, headers={"Content-Type": "text/html"},
                text="<html><body>Botteghe artigiani negozi marchi</body></html>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=3386,
                place_name="Mercato",
                website="https://example.org/",
                page_type="general",
                query="shops stores brands directory botteghe artigiani",
                client=client,
                resolver=public_resolver,
            )

        self.assertEqual(result.source_url, "https://example.org/botteghe/")
        self.assertIn("marchi", result.text or "")
        self.assertIn("https://example.org/botteghe/", requested)

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

    def test_general_query_can_follow_italian_shopping_alias_link(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text=(
                        "<html><body>"
                        "<a href='/torino/botteghe/'>Scopri gli artigiani</a>"
                        "<a href='/eventi/'>Appuntamenti</a>"
                        "</body></html>"
                    ),
                )
            self.assertEqual(request.url.path, "/torino/botteghe/")
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><body>Botteghe e artigiani del mercato</body></html>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=3386,
                place_name="Mercato Centrale Torino",
                website="https://example.org/",
                page_type="general",
                query="shops stores brands directory men women kids collections",
                client=client,
                resolver=public_resolver,
            )

        self.assertEqual(requested, ["https://example.org/", "https://example.org/torino/botteghe/"])
        self.assertIn("artigiani", result.text or "")

    def test_general_query_can_follow_italian_food_alias_link(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            if request.url.path == "/":
                return httpx.Response(
                    200,
                    headers={"Content-Type": "text/html"},
                    text="<html><body><a href='/cucina/'>La cucina</a></body></html>",
                )
            self.assertEqual(request.url.path, "/cucina/")
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text="<html><body>Menu e opzioni vegetariane</body></html>",
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=1015,
                place_name="Cafe",
                website="https://example.org/",
                page_type="general",
                query="menu vegetarian vegan dietary",
                client=client,
                resolver=public_resolver,
            )

        self.assertEqual(requested, ["https://example.org/", "https://example.org/cucina/"])
        self.assertIn("vegetariane", result.text or "")

    def test_general_query_does_not_follow_unrelated_generic_hint(self):
        requested: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            requested.append(str(request.url))
            return httpx.Response(
                200,
                headers={"Content-Type": "text/html"},
                text=(
                    "<html><body>"
                    "<a href='/shop/'>Shop</a>"
                    "<p>Welcome to the museum.</p>"
                    "</body></html>"
                ),
            )

        with httpx.Client(transport=httpx.MockTransport(handler)) as client:
            result = fetch_official_site(
                place_id=76,
                place_name="Museum",
                website="https://example.org/",
                page_type="general",
                query="accessibility wheelchair disabled barrier accessible",
                client=client,
                resolver=public_resolver,
            )

        self.assertEqual(requested, ["https://example.org/"])
        self.assertEqual(result.source_url, "https://example.org/")

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
