import ast
import copy
import types
import unittest
from datetime import datetime
from pathlib import Path

from pytz import UTC


MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "users" / "pwdmanager.py"


def load_ics_talks():
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    nodes = []
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "ics_talks":
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    mini = ast.Module(body=nodes, type_ignores=[])
    captured = {}

    def talks_search(query, seminar_dict=None):
        captured["query"] = copy.deepcopy(query)
        return []

    ns = {
        "talks_search": talks_search,
        "all_seminars": lambda: {},
        "datetime": datetime,
        "timedelta": __import__("datetime").timedelta,
        "UTC": UTC,
    }
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns["ics_talks"], captured


class IcsTombstoneTests(unittest.TestCase):
    def test_tombstones_excluded(self):
        ics_talks, captured = load_ics_talks()
        fake_self = types.SimpleNamespace(
            talks_query=[{"seminar_id": "vantage", "seminar_ctr": {"$in": [72]}}],
            seminar_subscriptions=["vantage"],
            talk_exclusions={},
            ics_limit_past=True,
            ics_limit_future=False,
        )
        self.assertEqual(ics_talks.__get__(fake_self)(), [])
        self.assertEqual(
            captured["query"].get("seminar_ctr"), {"$gt": 0},
            "reschedule tombstones (negative ctr) must be filtered",
        )


if __name__ == "__main__":
    unittest.main()
