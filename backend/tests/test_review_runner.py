import unittest
from unittest.mock import patch

from app.llm.ollama import OllamaError
from app.services.review_runner import run_with_ollama_retries


class ReviewRunnerTests(unittest.TestCase):
    @patch("app.services.review_runner.time.sleep", return_value=None)
    def test_retry_recovers_after_one_ollama_failure(self, _sleep):
        outcomes = [OllamaError("timeout"), "ok"]
        calls = []

        def operation():
            calls.append(1)
            outcome = outcomes.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        result = run_with_ollama_retries(operation, attempts=2)

        self.assertEqual(result, "ok")
        self.assertEqual(len(calls), 2)

    @patch("app.services.review_runner.time.sleep", return_value=None)
    def test_retry_raises_after_attempt_budget_is_exhausted(self, _sleep):
        calls = []

        def operation():
            calls.append(1)
            raise OllamaError("timeout")

        with self.assertRaises(OllamaError):
            run_with_ollama_retries(operation, attempts=2)

        self.assertEqual(len(calls), 2)

    def test_retry_requires_positive_attempt_budget(self):
        with self.assertRaises(ValueError):
            run_with_ollama_retries(lambda: "ok", attempts=0)


if __name__ == "__main__":
    unittest.main()
