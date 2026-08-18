import unittest

from app.core.languages import (
    LANGUAGE_NAMES,
    SUPPORTED_LANGUAGE_CODES,
    fallback_text,
)
from app.llm.prompts import ASSISTANT_RESPONSE_SYSTEM_PROMPT, INTENT_SYSTEM_PROMPT
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

    def test_prompts_make_selected_language_authoritative(self) -> None:
        for language in SUPPORTED_LANGUAGE_CODES:
            self.assertIn(language, INTENT_SYSTEM_PROMPT)
        self.assertIn("application-owned and authoritative", ASSISTANT_RESPONSE_SYSTEM_PROMPT)
        self.assertIn("only in that language", ASSISTANT_RESPONSE_SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
