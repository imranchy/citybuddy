import unittest
from unittest.mock import MagicMock, patch

from app.db.bootstrap import REQUIRED_EXTENSIONS, ensure_required_extensions


class DatabaseBootstrapTests(unittest.TestCase):
    def test_required_extensions_include_postgis_and_vector(self) -> None:
        self.assertEqual(REQUIRED_EXTENSIONS, ("postgis", "vector"))

    def test_extension_bootstrap_executes_both_extensions(self) -> None:
        fake_engine = MagicMock()
        fake_connection = MagicMock()
        fake_engine.begin.return_value.__enter__.return_value = fake_connection

        ensure_required_extensions(fake_engine)

        statements = [str(call.args[0]) for call in fake_connection.execute.call_args_list]
        self.assertEqual(len(statements), 2)
        self.assertTrue(any("postgis" in statement for statement in statements))
        self.assertTrue(any("vector" in statement for statement in statements))


if __name__ == "__main__":
    unittest.main()
