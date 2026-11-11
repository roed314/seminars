import ast
import bisect
import copy
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from pytz import UTC


ROOT = Path(__file__).resolve().parents[1]
PWD = ROOT / "seminars" / "users" / "pwdmanager.py"


def load_user_methods(*names):
    """Extract SeminarsUser methods, binding them to a throwaway class."""
    source = PWD.read_text()
    module = ast.parse(source)
    wanted = set(names)
    fns = {}
    for node in ast.walk(module):
        if isinstance(node, ast.ClassDef) and node.name == "SeminarsUser":
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name in wanted:
                    fn = copy.deepcopy(item)
                    fn.decorator_list = []
                    fns[item.name] = fn
    assert wanted <= set(fns), wanted - set(fns)
    mini = ast.Module(
        body=[fns[n] for n in names], type_ignores=[])
    ns = {
        "bisect": bisect,
        "defaultdict": __import__("collections").defaultdict,
        "datetime": datetime,
        "timedelta": timedelta,
        "UTC": UTC,
    }
    exec(compile(mini, str(PWD), "exec"), ns)
    cls = type("FakeUser", (), {})
    for name in names:
        fn = ns[name]
        if name in ("talk_exclusions", "talks_query", "seminar_subscriptions",
                    "talk_subscriptions"):
            setattr(cls, name, property(fn))
        else:
            setattr(cls, name, fn)
    return cls


def make_user(cls, **data):
    data.setdefault("seminar_subscriptions", [])
    data.setdefault("talk_subscriptions", {})
    data.setdefault("talk_exclusions", {})
    user = cls()
    user._data = data
    user._dirty = False
    return user


def bind(cls, name, user):
    return getattr(cls, name).__get__(user, cls)


class ExclusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.U = load_user_methods(
            "talk_exclusions", "is_excluded", "exclusion_add",
            "exclusion_remove", "seminar_subscriptions_remove",
            "talk_subscriptions_add")

    def test_add_remove_roundtrip(self):
        user = make_user(self.U)
        code, _ = bind(self.U, "exclusion_add", user)("STAGE", 1)
        self.assertEqual(code, 200)
        self.assertTrue(bind(self.U, "is_excluded", user)("STAGE", 1))
        self.assertFalse(bind(self.U, "is_excluded", user)("STAGE", 2))
        code, _ = bind(self.U, "exclusion_remove", user)("STAGE", 1)
        self.assertEqual(code, 200)
        self.assertFalse(bind(self.U, "is_excluded", user)("STAGE", 1))
        self.assertEqual(user._data["talk_exclusions"], {})

    def test_add_idempotent(self):
        user = make_user(self.U)
        bind(self.U, "exclusion_add", user)("STAGE", 1)
        bind(self.U, "exclusion_add", user)("STAGE", 1)
        self.assertEqual(user._data["talk_exclusions"], {"STAGE": [1]})

    def test_series_unsubscribe_purges_exclusions(self):
        user = make_user(self.U, seminar_subscriptions=["STAGE", "OTHER"],
                         talk_exclusions={"STAGE": [1]})
        bind(self.U, "seminar_subscriptions_remove", user)("STAGE")
        self.assertEqual(user._data["talk_exclusions"], {})
        self.assertEqual(user._data["seminar_subscriptions"], ["OTHER"])

    def test_explicit_favorite_clears_mute(self):
        user = make_user(self.U, talk_exclusions={"STAGE": [1]})
        bind(self.U, "talk_subscriptions_add", user)("STAGE", 1)
        self.assertEqual(user._data["talk_subscriptions"], {"STAGE": [1]})
        self.assertNotIn("STAGE", user._data.get("talk_exclusions", {}))

    def test_exclusions_survive_other_series(self):
        user = make_user(self.U, seminar_subscriptions=["STAGE"],
                         talk_exclusions={"STAGE": [1, 2]})
        bind(self.U, "exclusion_add", user)("OTHER", 9)
        self.assertEqual(user._data["talk_exclusions"],
                         {"STAGE": [1, 2], "OTHER": [9]})


class IcsExclusionTests(unittest.TestCase):
    def test_ics_talks_skips_muted_series_talks(self):
        source = PWD.read_text()
        module = ast.parse(source)
        for node in ast.walk(module):
            if isinstance(node, ast.ClassDef) and node.name == "SeminarsUser":
                for item in node.body:
                    if (isinstance(item, ast.FunctionDef)
                            and item.name == "ics_talks"
                            and isinstance(item.decorator_list[0], ast.Name)):
                        getter = copy.deepcopy(item)
                        getter.decorator_list = []
        mini = ast.Module(body=[getter], type_ignores=[])

        def talk(sid, ctr):
            t = types.SimpleNamespace(
                seminar_id=sid, seminar_ctr=ctr,
                start_time=datetime(2030, 1, 1, tzinfo=UTC))
            t.searchable = lambda: True
            t.user_can_edit = lambda user=None: False
            return t

        ns = {
            "talks_search": lambda query, seminar_dict=None: [
                talk("STAGE", 1), talk("STAGE", 2), talk("OTHER", 1)],
            "all_seminars": lambda: {},
            "datetime": datetime,
            "timedelta": timedelta,
            "UTC": UTC,
        }
        exec(compile(mini, str(PWD), "exec"), ns)
        U2 = load_user_methods("seminar_subscriptions", "talk_exclusions")
        user = make_user(U2, seminar_subscriptions=["STAGE", "OTHER"],
                         talk_exclusions={"STAGE": [1]})
        user.talks_query = [{"seminar_id": "OTHER",
                             "seminar_ctr": {"$in": [1]}}]
        user.ics_limit_past = False
        user.ics_limit_future = False
        res = ns["ics_talks"](user)
        self.assertEqual(
            sorted((t.seminar_id, t.seminar_ctr) for t in res),
            [("OTHER", 1), ("STAGE", 2)])


class WiringTests(unittest.TestCase):
    def test_routes_exist(self):
        text = (ROOT / "seminars" / "users" / "main.py").read_text()
        self.assertIn('/exclude/<shortname>/<int:ctr>', text)
        self.assertIn('/unexclude/<shortname>/<int:ctr>', text)

    def test_show_subscribe_mute_branch(self):
        source = (ROOT / "seminars" / "talk.py").read_text()
        self.assertIn("talk-exclusion", source)
        self.assertIn("current_user.talk_exclusions", source)

    def test_js_exclusion_endpoints(self):
        js = (ROOT / "seminars" / "static" / "seminars.js").read_text()
        self.assertIn("/user/exclude/", js)
        self.assertIn("/user/unexclude/", js)
        self.assertIn("talk-exclusion", js)

    def test_delete_purges(self):
        seminar_src = (ROOT / "seminars" / "seminar.py").read_text()
        self.assertIn("talk_exclusions", seminar_src)
        talk_src = (ROOT / "seminars" / "talk.py").read_text()
        self.assertIn("talk_exclusions", talk_src)

    def test_schema_documents_column(self):
        self.assertIn("talk_exclusions", (ROOT / "Schema.md").read_text())


if __name__ == "__main__":
    unittest.main()
