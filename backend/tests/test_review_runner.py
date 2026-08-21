import unittest
from unittest.mock import patch

from app.llm.vllm import VLLMError
from app.services.review_runner import run_with_model_retries


class ReviewRunnerTests(unittest.TestCase):
    @patch("app.services.review_runner.time.sleep", return_value=None)
    def test_retry_recovers_after_one_model_failure(self, _sleep):
        outcomes = [VLLMError("timeout"), "ok"]
        calls = []

        def operation():
            calls.append(1)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        result = run_with_model_retries(operation, attempts=2)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)

    @patch("app.services.review_runner.time.sleep", return_value=None)
    def test_retry_raises_after_attempt_budget_is_exhausted(self, _sleep):
        calls = []

        def operation():
            calls.append(1)
            raise VLLMError("timeout")

        with self.assertRaises(VLLMError):
            run_with_model_retries(operation, attempts=2)

        self.assertEqual(len(calls), 2)

    def test_retry_requires_positive_attempt_budget(self):
        with self.assertRaises(ValueError):
            run_with_model_retries(lambda: "ok", attempts=0)


if __name__ == "__main__":
    unittest.main()
