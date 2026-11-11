import ast
import copy
from pathlib import Path
import unittest


MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "homepage" / "main.py"


def load_parse_access():
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "parse_access":
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            break
    else:
        raise AssertionError("parse_access not found")
    mini = ast.Module(body=[fn], type_ignores=[])
    ns = {}
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns["parse_access"]


class ParseAccessTests(unittest.TestCase):
    def test_livestream_requires_online(self):
        parse_access = load_parse_access()
        query = {}
        parse_access({"access": "1"}, query)
        self.assertEqual(query, {
            "online": True,
            "access_control": {"$ne": 5},
            "live_link": {"$ne": ""},
        })

    def test_filter_off_leaves_query_alone(self):
        parse_access = load_parse_access()
        query = {}
        parse_access({}, query)
        self.assertEqual(query, {})


if __name__ == "__main__":
    unittest.main()
