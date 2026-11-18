import ast
import copy
from datetime import date
from pathlib import Path
import types
import unittest


MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "api" / "main.py"


def load_api_functions(*names):
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    wanted = set(names)
    nodes = []
    for node in module.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "MAX_SEARCH_PATTERN_LEN":
                    nodes.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name in wanted:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    mini = ast.Module(body=nodes, type_ignores=[])
    ns = {"MAX_TEXT_LEN": 8192}

    def process_user_input(inp, col, typ, tz=None):
        maxlength = {"weekdays": 12}
        if col in maxlength and len(inp) > maxlength[col]:
            raise ValueError("Input exceeds maximum length permitted")
        if typ == "smallint[]":
            raise ValueError("Unrecognized type smallint[]")
        if typ in ["int", "smallint", "bigint", "integer"]:
            return int(inp)
        if typ == "date":
            if isinstance(inp, str):
                return date.fromisoformat(inp)
            raise ValueError("Unable to parse date '%s'" % inp)
        if typ == "text":
            if inp and isinstance(inp, str):
                inp = inp.strip()
            return "\n".join(inp.splitlines())
        if typ == "text[]":
            if inp == "":
                return []
            if isinstance(inp, str):
                return [inp]
            if isinstance(inp, list):
                return [str(x) for x in inp]
            raise ValueError("Unrecognized input")
        return inp

    ns["process_user_input"] = process_user_input
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns


class SearchInputTests(unittest.TestCase):
    def test_weekday_array_filters(self):
        ns = load_api_functions(
            "_search_pattern",
            "_search_size_value",
            "_search_mod_value",
            "_search_array_value",
            "_process_search_condition",
            "process_search_input",
        )
        process_search_input = ns["process_search_input"]
        self.assertEqual(
            process_search_input({"$contains": [0]}, "weekdays", "smallint[]", "UTC"),
            {"$contains": [0]},
        )
        self.assertEqual(
            process_search_input({"$in": [[0], [2]]}, "weekdays", "smallint[]", "UTC"),
            {"$in": [[0], [2]]},
        )

    def test_mod_and_nested_size_conditions(self):
        ns = load_api_functions(
            "_search_pattern",
            "_search_size_value",
            "_search_mod_value",
            "_search_array_value",
            "_process_search_condition",
            "process_search_input",
        )
        process_search_input = ns["process_search_input"]
        self.assertEqual(
            process_search_input({"$mod": [0, 7]}, "frequency", "integer", "UTC"),
            {"$mod": [0, 7]},
        )
        self.assertEqual(
            process_search_input({"$size": {"$mod": [0, 2]}}, "topics", "text[]", "UTC"),
            {"$size": {"$mod": [0, 2]}},
        )

    def test_nested_size_null_but_not_scalar_null(self):
        ns = load_api_functions(
            "_search_pattern",
            "_search_size_value",
            "_search_mod_value",
            "_search_array_value",
            "_process_search_condition",
            "process_search_input",
        )
        process_search_input = ns["process_search_input"]
        self.assertEqual(
            process_search_input({"$size": {"$ne": None}}, "topics", "text[]", "UTC"),
            {"$size": {"$ne": None}},
        )
        with self.assertRaises(ValueError):
            process_search_input({"$size": None}, "topics", "text[]", "UTC")

    def test_search_series_returns_invalid_filter(self):
        ns = load_api_functions(
            "_search_pattern",
            "_search_size_value",
            "_search_mod_value",
            "_search_array_value",
            "_process_search_condition",
            "process_search_input",
            "search_series",
        )

        class APIError(Exception):
            def __init__(self, error=None, status=400):
                self.error = {} if error is None else error
                self.status = status

        ns["APIError"] = APIError
        ns["request"] = types.SimpleNamespace(method="GET")
        ns["get_request_args_json"] = lambda: {"name": {"$in": "bad"}}
        ns["current_user"] = types.SimpleNamespace(tz="UTC")
        ns["db"] = types.SimpleNamespace(
            seminars=types.SimpleNamespace(col_type={"name": "text"})
        )
        ns["version_error"] = lambda version: APIError({"code": "invalid_version"}, 400)
        ns["seminars_search"] = lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("seminars_search should not be called for invalid filters")
        )
        ns["str_jsonify"] = lambda result, callback=False: result

        with self.assertRaises(APIError) as ctx:
            ns["search_series"](0)
        self.assertEqual(ctx.exception.status, 400)
        self.assertEqual(ctx.exception.error.get("code"), "invalid_filter")


if __name__ == "__main__":
    unittest.main()
