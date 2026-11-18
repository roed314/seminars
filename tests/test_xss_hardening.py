import ast
import copy
import unittest
from functools import wraps
from markupsafe import Markup, escape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UTILS_PATH = ROOT / "seminars" / "utils.py"
API_MAIN_PATH = ROOT / "seminars" / "api" / "main.py"
HOMEPAGE_MAIN_PATH = ROOT / "seminars" / "homepage" / "main.py"
CREATE_MAIN_PATH = ROOT / "seminars" / "create" / "main.py"
USERS_MAIN_PATH = ROOT / "seminars" / "users" / "main.py"


def extract(path, names, extra_assigns=()):
    source = Path(path).read_text()
    module = ast.parse(source)
    wanted = set(names)
    nodes = []
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in extra_assigns:
                    nodes.append(node)
        elif isinstance(node, ast.ClassDef) and node.name in wanted:
            nodes.append(copy.deepcopy(node))
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    if len(nodes) < len(wanted):
        found = set()
        for node in nodes:
            found.add(node.name if not isinstance(node, ast.Assign) else "?")
        raise AssertionError("missing %s (found %s)" % (wanted - found, found))
    return nodes


def load_utils():
    flashed = []
    nodes = extract(
        UTILS_PATH,
        ["format_errmsg", "format_input_errmsg", "format_warning",
         "format_infomsg", "flash_error", "valid_jsonp_callback"],
        extra_assigns=("jsonp_callback_re",),
    )
    import re

    ns = {
        "re": re,
        "Markup": Markup,
        "escape": escape,
        "flash": lambda msg, cat=None: flashed.append((cat, msg)),
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(UTILS_PATH), "exec"), ns)
    return ns, flashed


def load_api_helpers():
    import json as json_mod

    nodes = extract(
        API_MAIN_PATH,
        ["format_error", "format_input_error", "str_jsonify",
         "_process_query_filters", "api_auth_required", "api_auth_optional",
         "_search_pattern", "_search_size_value", "_search_mod_value",
         "_search_array_value", "_process_search_condition",
         "process_search_input"],
        extra_assigns=("MAX_SEARCH_PATTERN_LEN",),
    )
    nodes += extract(UTILS_PATH, ["APIError"])
    responses = []

    class Response:
        def __init__(self, body, mimetype=None):
            self.body = body
            self.mimetype = mimetype

    def process_user_input(inp, col, typ, tz=None):
        # Minimal stand-in: the real one rejects NUL bytes the same way.
        if isinstance(inp, str) and "\x00" in inp:
            raise ValueError("Input contains invalid characters")
        if isinstance(inp, dict):
            raise ValueError("bad filter")
        return inp

    ns = {
        "json": json_mod,
        "escape": escape,
        "wraps": wraps,
        "Response": Response,
        "MAX_TEXT_LEN": 8192,
        "request": None,  # replaced per-test
        "SeminarsUser": None,  # replaced per-test
        "process_user_input": process_user_input,
        "valid_jsonp_callback": load_utils()[0]["valid_jsonp_callback"],
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(API_MAIN_PATH), "exec"), ns)
    return ns, responses


def load_homepage_parsers():
    flashed = []
    nodes = extract(
        HOMEPAGE_MAIN_PATH,
        ["parse_topic", "parse_institution_sem", "parse_language"],
    )
    ns = {
        "flash_error": lambda msg, *args: flashed.append((msg, args)),
        "topdomain": lambda: "researchseminars.org",
    }
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(HOMEPAGE_MAIN_PATH), "exec"), ns)
    return ns, flashed


class FormatEscapeTests(unittest.TestCase):
    def test_format_errmsg_escapes_args(self):
        ns, _ = load_utils()
        out = str(ns["format_errmsg"]("Hello %s", "<script>alert(1)</script>"))
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_format_errmsg_percent_in_template_does_not_raise(self):
        # Regression test for #964: str(err) containing % (e.g. "%2527")
        # used to raise TypeError -> 500.
        ns, _ = load_utils()
        out = str(ns["format_errmsg"]("Could not parse recent edit input %s. Error: 1\x00%2527%2522", "1\x00abc"))
        self.assertIn("Error:", out)
        self.assertIn("1", out)  # rendered, not raised

    def test_format_errmsg_fallback_escapes_template(self):
        ns, _ = load_utils()
        out = str(ns["format_errmsg"]("<script>%s</script> %s", "a"))
        self.assertNotIn("<script>", out)

    def test_format_input_errmsg_escapes_err(self):
        ns, _ = load_utils()
        out = str(ns["format_input_errmsg"](
            ValueError("bad <script>alert(1)</script>"), '"><img src=x>', "title"))
        self.assertNotIn("<script>", out)
        self.assertNotIn("<img", out)
        self.assertIn("Unable to process input", out)

    def test_flash_error_percent_template_no_crash(self):
        ns, flashed = load_utils()
        ns["flash_error"]("Could not parse recent edit input %s. Error: " + "1%00%2527", "1abc")
        self.assertEqual(len(flashed), 1)
        self.assertEqual(flashed[0][0], "error")

    def test_valid_jsonp_callback(self):
        ns, _ = load_utils()
        valid = ns["valid_jsonp_callback"]
        for good in ["foo", "foo.bar", "$x", "_x1", "jQuery123"]:
            self.assertTrue(valid(good), good)
        for bad in ["alert(1)", "foo-bar", "1abc", "a b", "", "foo;bar", "<script>"]:
            self.assertFalse(valid(bad), bad)


class ApiFormatTests(unittest.TestCase):
    def test_format_error_escapes(self):
        ns, _ = load_api_helpers()
        out = ns["format_error"]("bad %s", "<script>")
        self.assertNotIn("<script>", out)
        self.assertIn("&lt;script&gt;", out)

    def test_format_error_fallback_no_crash(self):
        ns, _ = load_api_helpers()
        out = ns["format_error"]("100% <b>oops</b>", "a", "b")
        self.assertNotIn("<b>", out)

    def test_format_input_error_escapes_all(self):
        ns, _ = load_api_helpers()
        out = ns["format_input_error"]("<script>e</script>", "<img>", "col<script>")
        self.assertNotIn("<script>", out)
        self.assertNotIn("<img>", out)


class JsonpTests(unittest.TestCase):
    def test_str_jsonify_valid_callback(self):
        ns, _ = load_api_helpers()
        resp = ns["str_jsonify"]({"a": 1}, "myCallback.foo")
        self.assertEqual(resp.mimetype, "application/javascript")
        self.assertTrue(resp.body.startswith("myCallback.foo("))

    def test_str_jsonify_invalid_callback_400(self):
        ns, _ = load_api_helpers()
        APIError = ns["APIError"]
        for bad in ["alert(1)", "foo-bar", "1abc", "a;b", "foo bar"]:
            with self.assertRaises(APIError) as ctx:
                ns["str_jsonify"]({"a": 1}, bad)
            self.assertEqual(ctx.exception.status, 400)

    def test_str_jsonify_no_callback(self):
        ns, _ = load_api_helpers()
        resp = ns["str_jsonify"]({"a": 1})
        self.assertEqual(resp.mimetype, "application/json")


class QueryFilterTests(unittest.TestCase):
    def test_nul_filter_rejected_400(self):
        ns, _ = load_api_helpers()
        APIError = ns["APIError"]
        with self.assertRaises(APIError) as ctx:
            ns["_process_query_filters"]({"title": "a\x00b"}, {"title": "text"}, "UTC")
        self.assertEqual(ctx.exception.status, 400)

    def test_unknown_column_rejected(self):
        ns, _ = load_api_helpers()
        APIError = ns["APIError"]
        with self.assertRaises(APIError):
            ns["_process_query_filters"]({"nope": "x"}, {"title": "text"}, "UTC")

    def test_clean_filter_passes_through(self):
        ns, _ = load_api_helpers()
        q = {"title": "zeta functions"}
        ns["_process_query_filters"](q, {"title": "text"}, "UTC")
        self.assertEqual(q, {"title": "zeta functions"})


class ApiAuthTests(unittest.TestCase):
    def _request_with_auth(self, ns, header):
        ns["request"] = type("R", (), {"headers": {"authorization": header}})()

    def test_nul_email_401(self):
        ns, _ = load_api_helpers()
        called = []

        class FakeUser:
            def __init__(self, email=None, uid=None):
                called.append(email)
                raise AssertionError("must not reach DB with NUL input")

        ns["SeminarsUser"] = FakeUser
        for deco in ["api_auth_required", "api_auth_optional"]:
            self._request_with_auth(ns, "bad\x00@example.com token")
            with self.assertRaises(ns["APIError"]) as ctx:
                ns[deco](lambda **kw: None)()
            self.assertEqual(ctx.exception.status, 401)
        self.assertEqual(called, [])

    def test_db_error_becomes_401(self):
        ns, _ = load_api_helpers()

        class FakeUser:
            def __init__(self, email=None, uid=None):
                raise ValueError("bad input")

        ns["SeminarsUser"] = FakeUser
        self._request_with_auth(ns, "someone@example.com token")
        for deco in ["api_auth_required", "api_auth_optional"]:
            with self.assertRaises(ns["APIError"]) as ctx:
                ns[deco](lambda **kw: None)()
            self.assertEqual(ctx.exception.status, 401)


class HomepageParseTests(unittest.TestCase):
    def test_topic_nul_rejected(self):
        ns, flashed = load_homepage_parsers()
        query = {}
        ns["parse_topic"]({"topic": "math_NT\x00evil"}, query)
        self.assertEqual(query, {})
        self.assertEqual(len(flashed), 1)

    def test_topic_clean_accepted(self):
        ns, _ = load_homepage_parsers()
        query = {}
        ns["parse_topic"]({"topic": "math_NT"}, query)
        self.assertIn("topics", query)

    def test_institution_nul_rejected(self):
        ns, flashed = load_homepage_parsers()
        query = {}
        ns["parse_institution_sem"]({"institution": "MIT\x00x"}, query)
        self.assertEqual(query, {})
        self.assertEqual(len(flashed), 1)

    def test_language_nul_rejected(self):
        ns, flashed = load_homepage_parsers()
        query = {}
        ns["parse_language"]({"language": "en\x00"}, query)
        self.assertEqual(query, {})
        self.assertEqual(len(flashed), 1)

    def test_language_clean_accepted(self):
        ns, _ = load_homepage_parsers()
        query = {}
        ns["parse_language"]({"language": "en"}, query)
        self.assertEqual(query, {"language": "en"})


class WiringTests(unittest.TestCase):
    def test_no_preformatted_flash_error(self):
        for path in [CREATE_MAIN_PATH, HOMEPAGE_MAIN_PATH,
                     ROOT / "seminars" / "institution.py",
                     ROOT / "seminars" / "seminar.py",
                     ROOT / "seminars" / "talk.py"]:
            tree = ast.parse(Path(path).read_text())
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, "id", "") == "flash_error":
                    self.assertTrue(node.args, path)
                    first = node.args[0]
                    self.assertNotIsInstance(first, ast.BinOp, "%s: %s" % (path, ast.dump(first)[:120]))
                    self.assertNotIsInstance(first, ast.Call, "%s: %s" % (path, ast.dump(first)[:120]))

    def test_flash_error_str_err_uses_args_form(self):
        for path in [CREATE_MAIN_PATH]:
            src = Path(path).read_text()
            self.assertNotIn("flash_error(str(err))", src, path)

    def test_users_main_escapes_markup(self):
        src = USERS_MAIN_PATH.read_text()
        self.assertIn("escape(user.name)", src)
        self.assertIn("escape(user.email)", src)
        tree = ast.parse(src)
        found_nested_try = False
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "loginas":
                for sub in ast.walk(node):
                    if isinstance(sub, ast.ExceptHandler):
                        for sub2 in ast.walk(sub):
                            if isinstance(sub2, ast.Try):
                                found_nested_try = True
        self.assertTrue(found_nested_try, "loginas needs nested try/except")

    def test_jsonp_validated_both_routes(self):
        for path in [API_MAIN_PATH, HOMEPAGE_MAIN_PATH]:
            src = Path(path).read_text()
            self.assertIn("valid_jsonp_callback", src, path)

    def test_search_talks_validates_filters(self):
        src = API_MAIN_PATH.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name == "search_talks":
                body = ast.dump(node)
                self.assertIn("_process_query_filters", body)
                break
        else:
            self.fail("search_talks not found")

    def test_api_formatters_have_fallback(self):
        src = API_MAIN_PATH.read_text()
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in ("format_error", "format_input_error"):
                body = ast.dump(node)
                if node.name == "format_error":
                    self.assertIn("ExceptHandler", body)
                    self.assertIn("escape", body)


if __name__ == "__main__":
    unittest.main()
