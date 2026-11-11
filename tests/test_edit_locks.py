import ast
import copy
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pytz

MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "create" / "main.py"


def load_lock_helpers():
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    wanted = {"parse_edited_at", "edited_at_conflict"}
    nodes = []
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    assert {n.name for n in nodes} == wanted, "lock helpers not found in create/main.py"
    mini = ast.Module(body=nodes, type_ignores=[])
    ns = {"datetime": datetime, "pytz": pytz}
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns["parse_edited_at"], ns["edited_at_conflict"]


parse_edited_at, edited_at_conflict = load_lock_helpers()


class EditLockHelperTests(unittest.TestCase):
    def test_matching_iso_no_conflict(self):
        current = datetime(2026, 5, 1, 12, 0, 0, tzinfo=pytz.UTC)
        self.assertFalse(edited_at_conflict(current.isoformat(), current))

    def test_mismatched_conflict(self):
        current = datetime(2026, 5, 1, 12, 0, 0, tzinfo=pytz.UTC)
        stale = (current - timedelta(hours=1)).isoformat()
        self.assertTrue(edited_at_conflict(stale, current))

    def test_missing_submitted_is_conflict(self):
        current = datetime(2026, 5, 1, 12, 0, 0, tzinfo=pytz.UTC)
        for bad in (None, "", "   ", "not-a-date"):
            with self.subTest(submitted=bad):
                self.assertTrue(edited_at_conflict(bad, current))

    def test_missing_current_disables_check(self):
        self.assertFalse(edited_at_conflict(None, None))
        self.assertFalse(edited_at_conflict("", None))

    def test_z_suffix_and_http_date(self):
        current = datetime(2026, 5, 1, 12, 0, 0, tzinfo=pytz.UTC)
        # naive Z is parsed as UTC; exact second match only if no micros
        naive_current = current.replace(microsecond=0)
        naive_zulu = naive_current.strftime("%Y-%m-%dT%H:%M:%S") + "Z"
        self.assertFalse(edited_at_conflict(naive_zulu, naive_current))
        http_date = naive_current.strftime("%a, %d %b %Y %H:%M:%S GMT")
        self.assertFalse(edited_at_conflict(http_date, naive_current))
        self.assertTrue(
            edited_at_conflict("Thu, 01 Jan 1970 00:00:00 GMT", naive_current)
        )

    def test_parse_roundtrip(self):
        current = datetime(2026, 5, 1, 12, 0, 0, 123456, tzinfo=pytz.UTC)
        self.assertEqual(parse_edited_at(current.isoformat()), current)
        self.assertIsNone(parse_edited_at(""))
        self.assertIsNone(parse_edited_at(None))


if __name__ == "__main__":
    unittest.main()
