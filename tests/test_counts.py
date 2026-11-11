import ast
import copy
import unittest
from pathlib import Path


UTILS_PATH = Path(__file__).resolve().parents[1] / "seminars" / "utils.py"

PENDING_PREQUERY = {"$or": [{"display": True}, {"by_api": False}]}


class FakeSQL:
    """Minimal stand-in for psycopg SQL/IdentifierWrapper composition."""

    def __init__(self, template, args=None):
        self.template = template
        self.args = args

    def join(self, items):
        return FakeSQL("JOIN(%s)[%s]" % (self.template, ",".join(map(str, items))))

    def format(self, *args):
        return FakeSQL(self.template, args)

    def __add__(self, other):
        return FakeSQL(
            "(%s + %s)" % (self.template, getattr(other, "template", other))
        )

    def __repr__(self):
        return "FakeSQL(%r)" % (self.template,)


class FakeCursor:
    def __init__(self, count="3"):
        self._count = count
        self.rowcount = 0

    def fetchone(self):
        return (self._count,)


class FakeTable:
    search_cols = ["shortname", "display"]
    search_table = "seminars"

    def __init__(self):
        self.built = []
        self.parsed = []
        self.executed = []

    def _build_query(self, query, *args, **kwargs):
        self.built.append((copy.deepcopy(query), args, kwargs))
        return ("QSTR", ["qval"])

    def _parse_dict(self, query):
        self.parsed.append(copy.deepcopy(query))
        return ("PQSTR", ["pqval"])

    def _execute(self, stmt, values, **kwargs):
        self.executed.append((stmt, list(values), kwargs))
        return FakeCursor()


def load_counter_functions():
    source = UTILS_PATH.read_text()
    module = ast.parse(source)
    wanted = {"_distinct_table", "count_distinct", "search_distinct"}
    nodes = []
    for node in module.body:
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    mini = ast.Module(body=nodes, type_ignores=[])
    ns = {
        "SQL": FakeSQL,
        "IdentifierWrapper": lambda name: FakeSQL("IDENT(%s)" % (name,)),
        "Placeholder": lambda: "PLACEHOLDER",
        "parse_projection": lambda table, projection: ("id",),
    }
    exec(compile(mini, str(UTILS_PATH), "exec"), ns)
    return ns


class CountPrefilterTests(unittest.TestCase):
    def test_count_applies_pending_prefilter(self):
        ns = load_counter_functions()
        table = FakeTable()
        counter = FakeSQL("counter")
        self.assertEqual(ns["count_distinct"](table, counter, {}), 3)
        # the display/by_api prefilter must hit the counter query too (#636:
        # count said 45 where search said 0 because pending rows were counted)
        self.assertEqual(table.parsed, [PENDING_PREQUERY])
        stmt, values, _ = table.executed[-1]
        self.assertEqual(values, ["pqval", "qval"])
        tbl = stmt.args[1]
        self.assertIn("WHERE", tbl.template)

    def test_count_include_pending_skips_prefilter(self):
        ns = load_counter_functions()
        table = FakeTable()
        ns["count_distinct"](table, FakeSQL("counter"), {}, include_pending=True)
        self.assertEqual(table.parsed, [])
        stmt, values, _ = table.executed[-1]
        self.assertEqual(values, ["qval"])
        self.assertNotIn("WHERE", stmt.args[1].template)

    def test_count_include_deleted(self):
        ns = load_counter_functions()
        table = FakeTable()
        ns["count_distinct"](table, FakeSQL("counter"), {})
        self.assertIn("deleted", table.built[-1][0])
        table2 = FakeTable()
        ns["count_distinct"](table2, FakeSQL("counter"), {}, include_deleted=True)
        self.assertNotIn("deleted", table2.built[-1][0])


class SearchRecountTests(unittest.TestCase):
    def run_search(self, ns, table, **kwds):
        iterator = lambda cur, cols, projection: iter([])  # noqa: E731
        info = {}
        res = ns["search_distinct"](
            table,
            FakeSQL("selecter"),
            FakeSQL("counter"),
            iterator,
            {},
            1,
            None,
            0,
            None,
            info,
            **kwds
        )
        return res, info

    def test_recount_forwards_pending_and_deleted_flags(self):
        ns = load_counter_functions()
        calls = []
        real_count = ns["count_distinct"]

        def recording_count(table, counter, query={}, include_deleted=False, include_pending=False):
            calls.append(
                {
                    "include_deleted": include_deleted,
                    "include_pending": include_pending,
                }
            )
            return real_count(
                table,
                counter,
                query,
                include_deleted=include_deleted,
                include_pending=include_pending,
            )

        ns["count_distinct"] = recording_count
        table = FakeTable()
        res, info = self.run_search(
            ns, table, include_deleted=True, include_pending=True
        )
        self.assertEqual(list(res), [])
        self.assertEqual(info["number"], 3)
        # both the SELECT and the recount must skip the pending prefilter
        self.assertEqual(table.parsed, [])
        self.assertEqual(
            calls,
            [{"include_deleted": True, "include_pending": True}],
        )

    def test_recount_applies_prefilter_when_pending_excluded(self):
        ns = load_counter_functions()
        table = FakeTable()
        res, info = self.run_search(ns, table)
        self.assertEqual(list(res), [])
        self.assertEqual(info["number"], 3)
        # one prefilter for the SELECT, one for the recount
        self.assertEqual(table.parsed, [PENDING_PREQUERY, PENDING_PREQUERY])
        for _stmt, values, _kw in table.executed:
            self.assertEqual(values[0], "pqval")

    def test_offset_recount_recursion_forwards_flags(self):
        ns = load_counter_functions()
        calls = []
        real_count = ns["count_distinct"]

        def recording_count(table, counter, query={}, include_deleted=False, include_pending=False):
            calls.append(
                {
                    "include_deleted": include_deleted,
                    "include_pending": include_pending,
                }
            )
            return real_count(
                table,
                counter,
                query,
                include_deleted=include_deleted,
                include_pending=include_pending,
            )

        ns["count_distinct"] = recording_count
        table = FakeTable()
        iterator = lambda cur, cols, projection: iter([])  # noqa: E731
        info = {}
        res = ns["search_distinct"](
            table,
            FakeSQL("selecter"),
            FakeSQL("counter"),
            iterator,
            {},
            1,
            5,
            10,
            None,
            info,
            True,  # include_deleted
            True,  # include_pending
        )
        self.assertEqual(list(res), [])
        self.assertEqual(info["number"], 3)
        self.assertEqual(info["start"], 0)
        self.assertEqual(
            calls,
            [
                {"include_deleted": True, "include_pending": True},
                {"include_deleted": True, "include_pending": True},
            ],
        )


if __name__ == "__main__":
    unittest.main()
