import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "seminars"


def cookie_writes_without_samesite():
    """All client- and server-side cookie writes must set SameSite (#840).

    Browsers reject cookies whose SameSite is missing/invalid in
    cross-site contexts (embed iframes); our preference cookies are
    first-party only, so SameSite=Lax is the correct explicit value.
    """
    bad = []
    for path in list((ROOT / "static").rglob("*.js")) + list(ROOT.rglob("*.html")):
        if not path.is_file():
            continue  # generated/minified assets absent from fresh checkouts
        if "daterangepicker" in path.parts or "jstree" in path.parts:
            continue  # vendored libs, not ours
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "document.cookie" in line and "=" in line and "includes(" not in line \
                    and "split(" not in line and ".split" not in line:
                if "document.cookie =" in line or "document.cookie=" in line:
                    if "SameSite" not in line:
                        bad.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    for path in list(ROOT.rglob("*.py")):
        for i, line in enumerate(path.read_text().splitlines(), 1):
            if "set_cookie(" in line and "samesite" not in line.lower():
                bad.append(f"{path.relative_to(ROOT)}:{i}: {line.strip()}")
    # eraseCookie must match the Path used when setting, or deletion fails
    erase = (ROOT / "static" / "seminars.js").read_text()
    m = re.search(r"function eraseCookie.*?{(.*?)}", erase, re.S)
    assert m, "eraseCookie not found"
    if "Path=/" not in m.group(1):
        bad.append("static/seminars.js: eraseCookie missing Path=/")
    return bad


class CookieSameSiteTests(unittest.TestCase):
    def test_all_cookie_writes_set_samesite(self):
        self.assertEqual(cookie_writes_without_samesite(), [])


if __name__ == "__main__":
    unittest.main()
