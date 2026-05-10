from __future__ import annotations

from pathlib import Path
import unittest

from rekry_tutka_agent.config import load_sources


class SourceConfigTests(unittest.TestCase):
    def test_default_sources_include_yle_and_duunitori(self) -> None:
        sources = load_sources(Path("config/sources.json"))
        names = {source.name for source in sources}

        self.assertIn("Yle - Tyoelama", names)
        self.assertIn("Yle - Tyonvalitys", names)
        self.assertIn("Duunitori Tyoelama - Rekrytointi", names)
        self.assertIn("Duunitori Tyoelama", names)


if __name__ == "__main__":
    unittest.main()
