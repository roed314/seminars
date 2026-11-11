import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1] / "seminars"

# Bare datetime.now() calls that are known-harmless (date-only comparison
# or display sorting with no tz semantics); see #742 triage.
ALLOWLIST = {
    ("homepage/main.py", 855),  # end_date is a date, not timestamptz
    ("utils.py", 270),          # naive_utcoffset display sort
}


def bare_now_calls():
    found = set()
    for path in sorted(ROOT.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text())
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "now"
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "datetime"
                    and not node.args and not node.keywords):
                rel = str(path.relative_to(ROOT)).replace("\\", "/")
                found.add((rel, node.lineno))
    return found


class NaiveNowTests(unittest.TestCase):
    def test_no_unexpected_naive_now(self):
        self.assertEqual(bare_now_calls(), ALLOWLIST)


if __name__ == "__main__":
    unittest.main()
