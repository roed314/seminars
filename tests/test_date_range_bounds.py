import unittest
from pathlib import Path


JS_PATH = (
    Path(__file__).resolve().parents[1] / "seminars" / "static" / "seminars.js"
)


class DateRangeBoundsTests(unittest.TestCase):
    def setUp(self):
        self.js = JS_PATH.read_text()

    def test_picker_bounds_stay_wide(self):
        # Issue #908: daterangepicker minDate/maxDate must not be clamped
        # to today via moment(), or typed pre-2020 dates get forced to now.
        self.assertNotRegex(self.js, r"\bminDate\s*=\s*moment\(\)")
        self.assertNotRegex(self.js, r"\bmaxDate\s*=\s*moment\(\)")

    def test_wide_bounds_present(self):
        self.assertIn("1970", self.js)
        self.assertIn("2050", self.js)
        self.assertRegex(
            self.js, r"var\s+minDate\s*=\s*['\"].*1970.*['\"]"
        )
        self.assertRegex(
            self.js, r"var\s+maxDate\s*=\s*['\"].*2050.*['\"]"
        )

    def test_ranges_still_filtered_by_past(self):
        # Shortcut ranges (not picker bounds) remain mode-specific.
        self.assertIn("delete ranges['Future']", self.js)
        self.assertIn("delete ranges['Past']", self.js)

    def test_daterangepicker_uses_bounds(self):
        self.assertRegex(self.js, r"minDate\s*:\s*minDate")
        self.assertRegex(self.js, r"maxDate\s*:\s*maxDate")

    def test_no_lenght_typo(self):
        self.assertNotIn("lenght", self.js)
        self.assertIn("dr.length", self.js)


if __name__ == "__main__":
    unittest.main()
