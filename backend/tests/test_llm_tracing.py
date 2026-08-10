import os
import unittest
from unittest.mock import patch

from app.llm.tracing import LangSmithConfigurationError, TraceConfig


class TraceConfigTests(unittest.TestCase):
    def test_tracing_is_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = TraceConfig.from_environment()
        self.assertFalse(config.enabled)
        self.assertEqual(config.project, "citybuddy-local-evaluation")

    def test_explicit_tracing_requires_api_key(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(LangSmithConfigurationError, "API_KEY"):
                TraceConfig.from_environment(enabled=True)

    def test_project_can_come_from_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"LANGSMITH_API_KEY": "test", "LANGSMITH_PROJECT": "portfolio-evals"},
            clear=True,
        ):
            config = TraceConfig.from_environment(enabled=True)
        self.assertTrue(config.enabled)
        self.assertEqual(config.project, "portfolio-evals")


if __name__ == "__main__":
    unittest.main()
