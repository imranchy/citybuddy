import unittest
from argparse import Namespace
from unittest.mock import patch

from app.core.cities import get_city
from scripts.run_daily_refresh import (
    PhaseResult,
    applied_refresh,
    command_for,
)


class DailyRefreshTests(unittest.TestCase):
    def setUp(self) -> None:
        self.arguments = Namespace(
            city="turin",
            place_limit_per_category=None,
            image_limit=None,
            review_limit=None,
            retry_attempts=2,
            review_timeout_seconds=None,
            index_batch_size=16,
            official_doc_place_limit=None,
            official_fact_place_limit=None,
            skip_official_docs=False,
            skip_official_facts=False,
            resume_place_run_id=None,
            resume_image_run_id=None,
            skip_images=False,
            apply=True,
        )
        self.city = get_city("turin")

    def test_command_for_uses_current_python_interpreter(self) -> None:
        command = command_for("scripts.index_place_evidence", "--city", "Torino")
        self.assertEqual(command[1:3], ["-m", "scripts.index_place_evidence"])
        self.assertEqual(command[-2:], ["--city", "Torino"])

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.has_eligible_places", return_value=True)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_apply_runs_safe_place_pipeline_before_images(
        self,
        collect_place_run,
        run_phase,
        has_eligible_places,
        has_eligible_images,
        collect_image_run,
    ) -> None:
        collect_place_run.return_value = (
            41,
            PhaseResult("OSM collection", "completed"),
        )
        collect_image_run.return_value = (
            52,
            PhaseResult("Wikimedia collection", "completed"),
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        phase_names = [result.name for result in results]
        self.assertEqual(
            phase_names,
            [
                "OSM collection",
                "Place review",
                "Place promotion",
                "Evidence indexing",
                "Official document refresh",
                "Official fact refresh",
                "Wikimedia collection",
                "Image promotion",
            ],
        )
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertEqual(
            executed,
            ["Place review", "Place promotion", "Evidence indexing", "Official document refresh", "Official fact refresh"],
        )
        has_eligible_places.assert_called_once_with(41)
        has_eligible_images.assert_called_once_with(52)

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_place_review_failure_closes_promotion_gate_but_indexing_and_images_continue(
        self,
        collect_place_run,
        run_phase,
        has_eligible_images,
        collect_image_run,
    ) -> None:
        collect_place_run.return_value = (
            41,
            PhaseResult("OSM collection", "completed"),
        )
        collect_image_run.return_value = (
            52,
            PhaseResult("Wikimedia collection", "completed"),
        )

        def phase_result(name, command):
            if name == "Place review":
                return PhaseResult(name, "failed", "model service unavailable")
            return PhaseResult(name, "completed")

        run_phase.side_effect = phase_result

        results = applied_refresh(self.arguments, self.city)

        promotion = next(result for result in results if result.name == "Place promotion")
        self.assertEqual(promotion.status, "skipped")
        self.assertIn("gate kept closed", promotion.detail)
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertNotIn("Place promotion", executed)
        self.assertIn("Evidence indexing", executed)
        collect_image_run.assert_called_once()

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_osm_collection_failure_does_not_block_independent_index_or_image_work(
        self,
        collect_place_run,
        run_phase,
        has_eligible_images,
        collect_image_run,
    ) -> None:
        collect_place_run.return_value = (
            None,
            PhaseResult("OSM collection", "failed", "source unavailable"),
        )
        collect_image_run.return_value = (
            52,
            PhaseResult("Wikimedia collection", "completed"),
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        self.assertEqual(results[1].name, "Place review")
        self.assertEqual(results[1].status, "skipped")
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertIn("Evidence indexing", executed)
        collect_image_run.assert_called_once()

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.has_eligible_places", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_empty_eligible_sets_are_idempotent_noops(
        self,
        collect_place_run,
        run_phase,
        has_eligible_places,
        has_eligible_images,
        collect_image_run,
    ) -> None:
        collect_place_run.return_value = (
            41,
            PhaseResult("OSM collection", "resumed"),
        )
        collect_image_run.return_value = (
            52,
            PhaseResult("Wikimedia collection", "resumed"),
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        place_promotion = next(
            result for result in results if result.name == "Place promotion"
        )
        image_promotion = next(
            result for result in results if result.name == "Image promotion"
        )
        self.assertEqual(place_promotion.status, "skipped")
        self.assertEqual(image_promotion.status, "skipped")
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertNotIn("Place promotion", executed)
        self.assertNotIn("Image promotion", executed)

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_official_document_refresh_is_independent_of_osm_failure(
        self,
        collect_place_run,
        run_phase,
        has_eligible_images,
        collect_image_run,
    ) -> None:
        collect_place_run.return_value = (
            None,
            PhaseResult("OSM collection", "failed", "source unavailable"),
        )
        collect_image_run.return_value = (
            52,
            PhaseResult("Wikimedia collection", "completed"),
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        official = next(
            result for result in results if result.name == "Official document refresh"
        )
        self.assertEqual(official.status, "completed")
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertIn("Official document refresh", executed)

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_official_document_refresh_can_be_skipped(
        self,
        collect_place_run,
        run_phase,
        has_eligible_images,
        collect_image_run,
    ) -> None:
        self.arguments.skip_official_docs = True
        collect_place_run.return_value = (
            None,
            PhaseResult("OSM collection", "failed", "source unavailable"),
        )
        collect_image_run.return_value = (
            52,
            PhaseResult("Wikimedia collection", "completed"),
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        official = next(
            result for result in results if result.name == "Official document refresh"
        )
        self.assertEqual(official.status, "skipped")
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertNotIn("Official document refresh", executed)

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_official_fact_refresh_is_independent_of_osm_failure(
        self, collect_place_run, run_phase, has_eligible_images, collect_image_run
    ) -> None:
        collect_place_run.return_value = (
            None, PhaseResult("OSM collection", "failed", "source unavailable")
        )
        collect_image_run.return_value = (
            52, PhaseResult("Wikimedia collection", "completed")
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        fact = next(result for result in results if result.name == "Official fact refresh")
        self.assertEqual(fact.status, "completed")
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertIn("Official fact refresh", executed)

    @patch("scripts.run_daily_refresh.collect_image_run")
    @patch("scripts.run_daily_refresh.has_eligible_images", return_value=False)
    @patch("scripts.run_daily_refresh.run_phase")
    @patch("scripts.run_daily_refresh.collect_place_run")
    def test_official_fact_refresh_can_be_skipped(
        self, collect_place_run, run_phase, has_eligible_images, collect_image_run
    ) -> None:
        self.arguments.skip_official_facts = True
        collect_place_run.return_value = (
            None, PhaseResult("OSM collection", "failed", "source unavailable")
        )
        collect_image_run.return_value = (
            52, PhaseResult("Wikimedia collection", "completed")
        )
        run_phase.side_effect = lambda name, command: PhaseResult(name, "completed")

        results = applied_refresh(self.arguments, self.city)

        fact = next(result for result in results if result.name == "Official fact refresh")
        self.assertEqual(fact.status, "skipped")
        executed = [call.args[0] for call in run_phase.call_args_list]
        self.assertNotIn("Official fact refresh", executed)


if __name__ == "__main__":
    unittest.main()
