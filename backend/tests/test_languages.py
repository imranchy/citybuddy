import unittest

from app.core.languages import (
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGE_CODES,
    fallback_text,
)
from app.llm.prompts import ASSISTANT_RESPONSE_SYSTEM_PROMPT, SEMANTIC_PLANNER_SYSTEM_PROMPT
from app.schemas.assistant import AssistantChatRequest


class LanguageConfigurationTests(unittest.TestCase):
    def test_required_languages_are_supported(self) -> None:
        self.assertEqual(
            SUPPORTED_LANGUAGE_CODES,
            ("en", "it", "pt", "de", "bn"),
        )
        self.assertEqual(set(LANGUAGE_NAMES), set(SUPPORTED_LANGUAGE_CODES))

    def test_request_schema_accepts_every_supported_language(self) -> None:
        for language in SUPPORTED_LANGUAGE_CODES:
            request = AssistantChatRequest(message="Recommend a museum", language=language)
            self.assertEqual(request.language, language)

    def test_fallback_copy_exists_for_every_supported_language(self) -> None:
        for language in SUPPORTED_LANGUAGE_CODES:
            self.assertTrue(fallback_text(language, "one_place"))
            self.assertTrue(fallback_text(language, "transit_disclaimer"))

    def test_prompts_define_dynamic_response_language_hierarchy(self) -> None:
        for language in SUPPORTED_LANGUAGE_CODES:
            self.assertIn(language, SEMANTIC_PLANNER_SYSTEM_PROMPT)
        self.assertIn("explicit response-language instruction", SEMANTIC_PLANNER_SYSTEM_PROMPT)
        self.assertIn("current message's language", SEMANTIC_PLANNER_SYSTEM_PROMPT)
        self.assertIn("ui_language", SEMANTIC_PLANNER_SYSTEM_PROMPT)
        self.assertIn("validated response language comes from the Qwen semantic plan", ASSISTANT_RESPONSE_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
