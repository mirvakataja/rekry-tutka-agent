from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from rekry_tutka_agent.cli import main


class CliTests(unittest.TestCase):
    def test_analyze_keywords_missing_api_key_exits_without_traceback(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            database = Path(tmpdir) / "agent.db"
            with patch.dict("os.environ", {}, clear=True):
                with self.assertRaises(SystemExit) as context:
                    main(["analyze-keywords", "--database", str(database)])

        self.assertEqual(context.exception.code, 1)

    def test_analyze_keywords_rejects_more_than_five_keywords(self) -> None:
        with self.assertRaises(SystemExit) as context:
            main(["analyze-keywords", "--max-keywords", "6"])

        self.assertEqual(context.exception.code, 2)


if __name__ == "__main__":
    unittest.main()
