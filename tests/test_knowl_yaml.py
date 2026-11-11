import unittest
from pathlib import Path

import yaml


KNOWLS_PATH = Path(__file__).resolve().parents[1] / "seminars" / "knowls.yaml"


class KnowlYamlTests(unittest.TestCase):
    def test_parses(self):
        data = yaml.safe_load(KNOWLS_PATH.read_text())
        self.assertIsInstance(data, dict)

    def test_export_knowls_present(self):
        data = yaml.safe_load(KNOWLS_PATH.read_text())
        for name in ("export", "export_series", "export_talk", "export_favorites"):
            with self.subTest(knowl=name):
                self.assertIn(name, data)
                self.assertIn("contents", data[name])
                self.assertTrue(data[name]["contents"].strip())


if __name__ == "__main__":
    unittest.main()
