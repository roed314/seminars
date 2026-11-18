import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOMEPAGE = ROOT / "seminars" / "homepage" / "main.py"
SEMINAR = ROOT / "seminars" / "seminar.py"
TALK = ROOT / "seminars" / "talk.py"
BROWSE = ROOT / "seminars" / "templates" / "browse_talks.html"


def parse(path):
    return ast.parse(path.read_text())


def funcs(tree):
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}


def src(path, node):
    return ast.get_source_segment(path.read_text(), node)


class PerfTests(unittest.TestCase):
    def test_talks_index_always_limits_sql(self):
        tree = parse(HOMEPAGE)
        fns = funcs(tree)
        self.assertIn("_talks_index", fns)
        body_src = src(HOMEPAGE, fns["_talks_index"])
        # dosearch must pass limit= to talks_search (SQL LIMIT 100 always)
        self.assertIn("talks_search(", body_src)
        self.assertIn("limit=", body_src)
        # no unlimited retry: dosearch(limit=None) must be gone
        self.assertNotIn("dosearch(limit=None)", body_src)
        # projection prune on list query
        self.assertIn("projection=", body_src)
        self.assertIn("talk_list_projection()", body_src)

    def test_list_projection_excludes_heavy_cols(self):
        tree = parse(TALK)
        fns = funcs(tree)
        self.assertIn("talk_list_projection", fns)
        text = TALK.read_text()
        self.assertIn("TALK_LIST_EXCLUDE", text)
        self.assertIn('"abstract"', text)
        self.assertIn('"comments"', text)
        proj_src = src(TALK, fns["talk_list_projection"])
        self.assertIn("TALK_LIST_EXCLUDE", proj_src)
        # list query must exclude abstract/comments
        home = HOMEPAGE.read_text()
        self.assertIn("talk_list_projection", home)
        self.assertIn("TALK_LIST_EXCLUDE", (TALK.read_text() + home))

    def test_dict_caches_have_ttl_and_invalidation(self):
        sem_text = SEMINAR.read_text()
        for name in ["_DICT_CACHE_TTL", "_cached_dict", "invalidate_seminar_cache"]:
            self.assertIn(name, sem_text, name)
        sem_tree = parse(SEMINAR)
        fns = funcs(sem_tree)
        for fname in ["all_seminars", "all_organizers", "all_institutions"]:
            self.assertIn(fname, fns)
            self.assertIn("_cached_dict", src(SEMINAR, fns[fname]), fname)
        # saves invalidate
        for fname in ["save", "save_admin", "save_organizers", "delete"]:
            found = False
            for node in ast.walk(sem_tree):
                if isinstance(node, ast.FunctionDef) and node.name == fname:
                    if "invalidate_seminar_cache" in src(SEMINAR, node):
                        found = True
            self.assertTrue(found, fname + " must invalidate cache")
        home_text = HOMEPAGE.read_text()
        self.assertIn("invalidate_shortnames_cache", home_text)
        self.assertIn("institutions_shortnames_ttl", home_text)
        inst_text = (ROOT / "seminars" / "institution.py").read_text()
        self.assertIn("invalidate_seminar_cache", inst_text)
        self.assertIn("invalidate_shortnames_cache", inst_text)

    def test_cached_dict_ttl_behavior_without_db(self):
        # Exec the real helper (no DB needed) and check TTL + invalidate.
        sem_tree = parse(SEMINAR)
        fns = funcs(sem_tree)
        ns = {"time": __import__("time")}
        ttl_node = None
        for node in sem_tree.body:
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    if isinstance(t, ast.Name) and t.id == "_DICT_CACHE_TTL":
                        ttl_node = node
        self.assertIsNotNone(ttl_node)
        mod = ast.Module(body=[ttl_node, fns["_cached_dict"], fns["invalidate_seminar_cache"]], type_ignores=[])
        # _cached_dict references module globals _dict_cache/_dict_cache_time
        exec(compile(mod, str(SEMINAR), "exec"), ns)
        ns["_dict_cache"] = {}
        ns["_dict_cache_time"] = {}
        calls = []
        ns["_cached_dict"]("k", lambda: calls.append(1) or "v1")
        ns["_cached_dict"]("k", lambda: calls.append(1) or "v2")
        self.assertEqual(len(calls), 1)
        ns["invalidate_seminar_cache"]()
        ns["_cached_dict"]("k", lambda: calls.append(1) or "v3")
        self.assertEqual(len(calls), 2)
        self.assertEqual(ns["_cached_dict"]("k", lambda: "other"), "v3")

    def test_talk_list_projection_fallback_without_db(self):
        tree = parse(TALK)
        fns = funcs(tree)
        # stub db with full cols including heavy ones
        import types

        stub_db = types.SimpleNamespace(
            talks=types.SimpleNamespace(search_cols=["title", "abstract", "comments", "speaker"])
        )
        ns = {"db": stub_db, "TALK_LIST_EXCLUDE": ("abstract", "comments")}
        exec(compile(ast.Module(body=[fns["talk_list_projection"]], type_ignores=[]), str(TALK), "exec"), ns)
        proj = ns["talk_list_projection"]()
        self.assertIn("title", proj)
        self.assertNotIn("abstract", proj)
        self.assertNotIn("comments", proj)
        # fallback path: db raises -> explicit list without heavy cols
        bad_db = types.SimpleNamespace(talks=types.SimpleNamespace(search_cols=None))
        # force exception by making search_cols raise on list()
        class BadCols:
            def __iter__(self):
                raise RuntimeError("no db")

        bad_db.talks.search_cols = BadCols()
        ns2 = {"db": bad_db, "TALK_LIST_EXCLUDE": ("abstract", "comments")}
        exec(compile(ast.Module(body=[fns["talk_list_projection"]], type_ignores=[]), str(TALK), "exec"), ns2)
        proj2 = ns2["talk_list_projection"]()
        self.assertNotIn("abstract", proj2)
        self.assertNotIn("comments", proj2)
        self.assertIn("title", proj2)

    def test_counters_endpoint_exists(self):
        home = HOMEPAGE.read_text()
        self.assertIn("talks_counters", home)
        self.assertIn("/talks_counters", home)
        self.assertIn("_talks_counters_light", home)
        self.assertIn('projection=["topics", "language"]', home)

    def test_knowl_lazy_and_striping_preserved(self):
        talk_text = TALK.read_text()
        # lazy knowl path preserved for list view
        self.assertIn('knowl="talk/{seminar_id}/{talkid}"', talk_text)
        # rescheduled lookup uses pruned projection
        self.assertIn("talk_list_projection()", talk_text)
        home_text = HOMEPAGE.read_text()
        # asblock semantics kept
        self.assertIn("truncateasblock", home_text)
        self.assertIn("start_time != last_time", home_text)
        # visible_counter striping kept
        self.assertIn("visible_counter", home_text)
        self.assertIn("oddrow", home_text)
        self.assertIn("evenrow", home_text)
        # infinite-scroll passes visible counter
        browse = BROWSE.read_text()
        self.assertIn("visibletalks()", browse)
        self.assertIn("?visible=", browse)

    def test_cleanse_tolerates_pruned_projection(self):
        talk_text = TALK.read_text()
        self.assertIn("getattr(self, col, None)", talk_text)


if __name__ == "__main__":
    unittest.main()
