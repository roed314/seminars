import ast
import copy
from pathlib import Path
import unittest


MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "api" / "main.py"


class APIError(Exception):
    def __init__(self, error=None, status=400):
        super().__init__(str(error))
        self.error = {} if error is None else error
        self.status = status


def load_api_functions(*names):
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    wanted = set(names)
    nodes = []
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name in wanted:
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            nodes.append(fn)
    mini = ast.Module(body=nodes, type_ignores=[])
    ns = {
        "APIError": APIError,
        "MAX_SLOTS": 12,
        "short_weekdays": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
    }
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns


class SlotProcessingTests(unittest.TestCase):
    def test_valid_slots(self):
        ns = load_api_functions("_process_slots")
        raw = {}
        ns["_process_slots"](["Mon 10:00-11:00", "Wed 14:00-15:00"], raw)
        self.assertEqual(raw["weekday0"], "0")
        self.assertEqual(raw["time_slot0"], "10:00-11:00")
        self.assertEqual(raw["weekday1"], "2")
        self.assertEqual(raw["num_slots"], 2)
        self.assertEqual(raw["weekday11"], "")
        self.assertEqual(raw["time_slot11"], "")

    def test_malformed_slots_rejected(self):
        ns = load_api_functions("_process_slots")
        for bad in (["Monday"], [""], ["   "], ["Foo 10:00-11:00"],
                    "Mon 10:00", ["Mon 10:00"] * 13, [123]):
            with self.subTest(slots=bad):
                with self.assertRaises(APIError) as ctx:
                    ns["_process_slots"](bad, {})
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.error.get("code"),
                                 "processing_error")


class DeletedGuardTests(unittest.TestCase):
    def test_deleted_rejected(self):
        ns = load_api_functions("_reject_deleted_keys")
        for bad in ({"deleted": True}, {"deleted": False},
                    {"deleted_with_seminar": True},
                    {"deleted": True, "title": "x"}):
            with self.subTest(raw=bad):
                with self.assertRaises(APIError) as ctx:
                    ns["_reject_deleted_keys"](dict(bad))
                self.assertEqual(ctx.exception.status, 400)
                self.assertEqual(ctx.exception.error.get("code"),
                                 "deleted_prohibited")

    def test_clean_input_passes(self):
        ns = load_api_functions("_reject_deleted_keys")
        ns["_reject_deleted_keys"]({"title": "x", "slots": []})


if __name__ == "__main__":
    unittest.main()
