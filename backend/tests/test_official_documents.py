import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services.official_documents import (
    _chunks,
    collect_official_document_candidates,
    resolve_topics,
)
from app.services.official_site import OfficialSiteEvidence


class _ScalarResult:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _Database:
    def __init__(self, places):
        self.places = places

    def scalars(self, statement):
        return _ScalarResult(self.places)


class OfficialDocumentTests(unittest.TestCase):
    def test_unknown_topic_is_rejected_before_retrieval(self) -> None:
        with self.assertRaises(ValueError):
            resolve_topics(["anything-on-the-web"])

    def test_chunks_are_bounded(self) -> None:
        chunks = _chunks("Sentence. " * 1000)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= 1800 for chunk in chunks))

    @patch("app.services.official_documents.get_official_place_page")
    def test_collection_uses_reviewed_place_id_and_never_a_url(self, retrieve) -> None:
        place = SimpleNamespace(
            id=5,
            name="Armeria Reale",
            city="Torino",
            website="https://official.example",
        )
        retrieve.return_value = OfficialSiteEvidence(
            place_id=5,
            place_name="Armeria Reale",
            page_type="general",
            official_host="official.example",
            source_url="https://official.example/accessibility",
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            verified=True,
            reason=None,
            title="Accessibility",
            text="Wheelchair access is available at the main entrance.",
            truncated=False,
        )

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["accessibility"],
        )

        self.assertEqual(len(collection.candidates), 1)
        candidate = collection.candidates[0]
        self.assertEqual(candidate.source_type, "official_site")
        self.assertEqual(candidate.content_type, "accessibility")
        self.assertEqual(candidate.source_fetched_at.year, 2026)
        self.assertEqual(candidate.source_url, "https://official.example/accessibility")
        retrieve.assert_called_once_with(
            unittest.mock.ANY,
            place_id=5,
            page_type="general",
            query="accessibility wheelchair disabled barrier accessible",
        )
        self.assertNotIn("website", retrieve.call_args.kwargs)

    @patch("app.services.official_documents.get_official_place_page")
    def test_unrelated_official_page_is_not_indexed_under_topic(self, retrieve) -> None:
        place = SimpleNamespace(
            id=1,
            name="Museo Montagna",
            city="Torino",
            website="https://www.museomontagna.org/",
        )
        retrieve.return_value = OfficialSiteEvidence(
            place_id=1,
            place_name="Museo Montagna",
            page_type="general",
            official_host="museomontagna.org",
            source_url="https://www.museomontagna.org/shop/",
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            verified=True,
            reason=None,
            title="Shop",
            text="Books, gifts and museum merchandise are available in our shop.",
            truncated=False,
        )

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["accessibility"],
        )

        self.assertEqual(collection.candidates, [])
        self.assertEqual(len(collection.failures), 1)
        self.assertIn("no topic-relevant official content", collection.failures[0])
        self.assertEqual(collection.completed_topics[(1, "accessibility")], set())


    @patch("app.services.official_documents.get_official_place_page")
    def test_footer_shop_link_does_not_make_unrelated_page_a_shopping_directory(self, retrieve) -> None:
        place = SimpleNamespace(
            id=1,
            name="Museo Montagna",
            city="Torino",
            website="https://www.museomontagna.org/",
        )
        retrieve.return_value = OfficialSiteEvidence(
            place_id=1,
            place_name="Museo Montagna",
            page_type="general",
            official_host="museomontagna.org",
            source_url="https://www.museomontagna.org/area-documentazione/",
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            verified=True,
            reason=None,
            title="Area documentazione",
            text="Archive and documentation centre. Visit our shop.",
            truncated=False,
        )

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["shopping_directory"],
        )

        self.assertEqual(collection.candidates, [])
        self.assertEqual(collection.completed_topics[(1, "shopping_directory")], set())
        self.assertIn("no topic-relevant official content", collection.failures[0])

    def test_relevance_terms_do_not_match_inside_unrelated_words(self) -> None:
        from app.services.official_documents import _contains_relevance_term

        self.assertFalse(_contains_relevance_term("documentation centre", "men"))
        self.assertFalse(_contains_relevance_term("shopping centre", "shop"))
        self.assertTrue(_contains_relevance_term("men and women", "men"))
        self.assertTrue(_contains_relevance_term("informazioni disabilità", "disabil"))

    @patch("app.services.official_documents.get_official_place_page")
    def test_repeated_homepage_is_not_indexed_for_every_topic(self, retrieve) -> None:
        place = SimpleNamespace(
            id=8,
            name="Example Mall",
            city="Torino",
            website="https://mall.example",
        )
        retrieve.return_value = OfficialSiteEvidence(
            place_id=8,
            place_name="Example Mall",
            page_type="general",
            official_host="mall.example",
            source_url="https://mall.example/",
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            verified=True,
            reason=None,
            title="Mall",
            text=(
                "Parking and family facilities are available. "
                "Browse our stores and brands before your visit."
            ),
            truncated=False,
        )

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["visitor_services", "shopping_directory"],
        )

        self.assertEqual(len(collection.candidates), 1)

    @patch("app.services.official_documents.get_official_place_page")
    def test_museum_does_not_crawl_shopping_directory_or_dietary_policy(self, retrieve) -> None:
        place = SimpleNamespace(
            id=2,
            name="Example Museum",
            city="Torino",
            category="museum",
            website="https://museum.example",
        )

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["shopping_directory", "dietary_policy"],
        )

        self.assertEqual(collection.candidates, [])
        self.assertEqual(collection.failures, [])
        self.assertEqual(collection.completed_topics[(2, "shopping_directory")], set())
        self.assertEqual(collection.completed_topics[(2, "dietary_policy")], set())
        retrieve.assert_not_called()

    @patch("app.services.official_documents.get_official_place_page")
    def test_shopping_centre_can_collect_shopping_directory(self, retrieve) -> None:
        place = SimpleNamespace(
            id=12,
            name="Example Mall",
            city="Torino",
            category="shopping_centre",
            website="https://mall.example",
        )
        retrieve.return_value = OfficialSiteEvidence(
            place_id=12,
            place_name="Example Mall",
            page_type="general",
            official_host="mall.example",
            source_url="https://mall.example/stores/",
            fetched_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
            verified=True,
            reason=None,
            title="Stores and brands",
            text="Browse our stores and brands for men, women and kids.",
            truncated=False,
        )

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["shopping_directory"],
        )

        self.assertEqual(len(collection.candidates), 1)
        self.assertEqual(collection.candidates[0].content_type, "shopping_directory")
        retrieve.assert_called_once()

    @patch("app.services.official_documents.get_official_place_page")
    def test_failed_topic_is_isolated(self, retrieve) -> None:
        place = SimpleNamespace(
            id=9,
            name="Example",
            city="Torino",
            website="https://example.org",
        )
        retrieve.side_effect = ValueError("timeout")

        collection = collect_official_document_candidates(
            _Database([place]),
            city="Torino",
            topic_keys=["accessibility"],
        )

        self.assertEqual(collection.candidates, [])
        self.assertEqual(len(collection.failures), 1)
        self.assertIn("timeout", collection.failures[0])


if __name__ == "__main__":
    unittest.main()
