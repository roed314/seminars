import ast
import copy
import re
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

import pytz
from dateutil.parser import parse as parse_time

MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "create" / "bulk_export.py"

FUNCS = [
    "get_managed_series_ids",
    "parse_series_param",
    "parse_pagination",
    "parse_daterange_to_query",
    "build_talks_query",
    "is_talk_visible_to_organizer",
    "filter_authorized_talks",
    "needs_split",
    "paginate_talks",
    "group_talks_by_series",
    "export_filename",
]

CONSTS = ["MAX_EXPORT_TALKS", "MAX_EXPORT_BYTES", "MAX_PAGE_LIMIT"]


def load_ns():
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    nodes = []
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in CONSTS:
                    nodes.append(copy.deepcopy(node))
        elif isinstance(node, ast.FunctionDef) and node.name in FUNCS:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    mini = ast.Module(body=nodes, type_ignores=[])
    shortname_re = re.compile("^[A-Za-z0-9_-]+$")
    ns = {
        "re": re,
        "datetime": datetime,
        "timedelta": timedelta,
        "parse_time": parse_time,
        "pytz": pytz,
        "allowed_shortname": lambda s: bool(shortname_re.match(s or "")),
    }
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns


NS = load_ns()


def make_talk(sid, searchable=False, editable=False):
    talk = types.SimpleNamespace(seminar_id=sid)
    talk.searchable = lambda: searchable
    try:
        talk.user_can_edit = lambda user=None: editable
    except Exception:
        pass
    return talk


class BulkExportTests(unittest.TestCase):
    def test_managed_ids_union_sorted(self):
        f = NS["get_managed_series_ids"]
        self.assertEqual(f(["b", "a", "b"], ["c", "a"]), ["a", "b", "c"])
        self.assertEqual(f([], []), [])
        self.assertEqual(f([None, ""], ["x"]), ["x"])

    def test_series_param_defaults_to_all(self):
        f = NS["parse_series_param"]
        managed = ["a", "b"]
        self.assertEqual(f(None, managed), ["a", "b"])
        self.assertEqual(f("", managed), ["a", "b"])
        self.assertEqual(f("a", managed), ["a"])
        self.assertEqual(f("a,b", managed), ["a", "b"])
        self.assertEqual(f("b, a, b", managed), ["b", "a"])

    def test_series_param_rejects_unauthorized(self):
        f = NS["parse_series_param"]
        with self.assertRaises(PermissionError):
            f("evil", ["a", "b"])
        with self.assertRaises(PermissionError):
            f("a,evil", ["a", "b"])

    def test_series_param_rejects_bad_input(self):
        f = NS["parse_series_param"]
        with self.assertRaises(ValueError):
            f("a\x00b", ["a\x00b"])
        with self.assertRaises(ValueError):
            f("bad id!", ["bad id!"])

    def test_build_query_includes_in_and_ctr(self):
        f = NS["build_talks_query"]
        now = pytz.UTC.localize(datetime(2030, 1, 1))
        q = f(["a", "b"], now=now)
        self.assertEqual(q["seminar_id"], {"$in": ["a", "b"]})
        self.assertEqual(q["seminar_ctr"], {"$gt": 0})
        self.assertNotIn("start_time", q)
        qp = f(["a"], past_only=True, now=now)
        self.assertEqual(qp["start_time"], {"$lte": now})
        qf = f(["a"], future_only=True, now=now)
        self.assertEqual(qf["end_time"], {"$gte": now})
        with self.assertRaises(ValueError):
            f([], now=now)

    def test_daterange_roundtrip(self):
        f = NS["parse_daterange_to_query"]
        tz = pytz.timezone("US/Eastern")
        upd, err = f("January 2, 2030 - January 5, 2030", tz)
        self.assertIsNone(err)
        self.assertIn("start_time", upd)
        self.assertIn("$gte", upd["start_time"])
        self.assertIn("$lte", upd["start_time"])
        upd2, err2 = f("", tz)
        self.assertIsNone(err2)
        self.assertEqual(upd2, {})
        _, err3 = f("a\x00b", tz)
        self.assertIsNotNone(err3)
        _, err4 = f("2020-01-01-2020-02-01-extra", tz)
        self.assertIsNotNone(err4)

    def test_authz_filter_no_leak(self):
        filt = NS["filter_authorized_talks"]
        user = object()
        talks = [
            make_talk("mine", searchable=True, editable=False),
            make_talk("mine", searchable=False, editable=True),
            make_talk("mine", searchable=False, editable=False),  # hidden, not editable
            make_talk("other", searchable=True, editable=False),  # public but not mine
        ]
        out = filt(talks, user, allowed_ids=["mine"])
        self.assertEqual(len(out), 2)
        self.assertTrue(all(t.seminar_id == "mine" for t in out))

    def test_needs_split_thresholds(self):
        f = NS["needs_split"]
        self.assertFalse(f(10, 100))
        self.assertTrue(f(901))
        self.assertTrue(f(10, 800 * 1024 + 1))
        self.assertFalse(f(900, 800 * 1024))

    def test_pagination(self):
        f = NS["paginate_talks"]
        seq = list(range(10))
        self.assertEqual(f(seq, offset=2, limit=3), [2, 3, 4])
        self.assertEqual(f(seq, offset=0, limit=None), seq)
        with self.assertRaises(ValueError):
            f(seq, offset=-1, limit=3)
        with self.assertRaises(ValueError):
            f(seq, offset=0, limit=0)

    def test_pagination_args(self):
        f = NS["parse_pagination"]
        self.assertEqual(f({}), (0, None))
        self.assertEqual(f({"offset": "5", "limit": "10"}), (5, 10))
        with self.assertRaises(ValueError):
            f({"offset": "-1"})
        with self.assertRaises(ValueError):
            f({"limit": "0"})

    def test_group_and_filename(self):
        g = NS["group_talks_by_series"]
        fn = NS["export_filename"]
        talks = [make_talk("b"), make_talk("a"), make_talk("b")]
        grouped = g(talks)
        self.assertEqual(sorted(grouped), ["a", "b"])
        self.assertEqual(len(grouped["b"]), 2)
        self.assertEqual(fn(["LATeN"]), "LATeN.ics")
        self.assertEqual(fn(["a", "b"]), "my-series.ics")


if __name__ == "__main__":
    unittest.main()
