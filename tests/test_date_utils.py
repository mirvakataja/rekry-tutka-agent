from __future__ import annotations

import unittest

from rekry_tutka_agent.date_utils import normalize_date, parse_date


class NormalizeDateTests(unittest.TestCase):
    def test_normalizes_rfc_822_to_utc_iso(self) -> None:
        self.assertEqual(
            normalize_date("Sun, 10 May 2026 01:00:00 +0300"),
            "2026-05-09T22:00:00+00:00",
        )

    def test_keeps_unknown_date_as_original_text(self) -> None:
        self.assertEqual(normalize_date("Spring 2026"), "Spring 2026")

    def test_empty_values_return_none(self) -> None:
        self.assertIsNone(normalize_date(None))
        self.assertIsNone(normalize_date("   "))

    def test_parse_date_returns_utc_datetime(self) -> None:
        parsed = parse_date("2026-05-10T01:00:00+03:00")

        self.assertEqual(parsed.isoformat(), "2026-05-09T22:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
