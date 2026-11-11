import ast
import copy
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CREATE_MAIN = ROOT / "seminars" / "create" / "main.py"


def load_helper():
    source = CREATE_MAIN.read_text()
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "_rerender_with_topics":
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            break
    else:
        raise AssertionError("_rerender_with_topics not found")
    mini = ast.Module(body=[fn], type_ignores=[])
    flashed = []
    rendered = {}

    def fake_render(template, **kwds):
        rendered["template"] = template
        rendered["kwds"] = kwds
        return (template, kwds)

    ns = {
        "flash": lambda msg, cat=None: flashed.append((cat, msg)),
        "render_template": fake_render,
        "clean_topics": lambda inp: ["echoed", inp],
    }
    exec(compile(mini, str(CREATE_MAIN), "exec"), ns)
    return ns["_rerender_with_topics"], flashed, rendered


class RerenderHelperTests(unittest.TestCase):
    def test_flashes_errors_and_echoes_topics(self):
        helper, flashed, rendered = load_helper()
        raw = {"topics": "['math_NT']"}
        helper("edit_talk.html", ["bad speaker", "bad date"], raw, talk="T")
        self.assertEqual(flashed, [("error", "bad speaker"), ("error", "bad date")])
        self.assertEqual(rendered["template"], "edit_talk.html")
        self.assertEqual(rendered["kwds"]["submitted_topics"], ["echoed", "['math_NT']"])
        self.assertEqual(rendered["kwds"]["talk"], "T")


class WiringTests(unittest.TestCase):
    def test_save_paths_rerender_instead_of_inputerror(self):
        source = CREATE_MAIN.read_text()
        module = ast.parse(source)
        for node in ast.walk(module):
            if isinstance(node, ast.FunctionDef) and node.name in ("save_seminar", "save_talk"):
                body = ast.dump(node)
                self.assertIn("_rerender_with_topics", body, node.name)
        # show_input_errors must no longer be used by the two save paths
        saves = [n for n in ast.walk(module)
                 if isinstance(n, ast.FunctionDef) and n.name in ("save_seminar", "save_talk")]
        self.assertEqual(len(saves), 2)
        for node in saves:
            for child in ast.walk(node):
                if isinstance(child, ast.Name) and child.id == "show_input_errors":
                    self.fail(node.name + " still uses show_input_errors")

    def test_templates_prefer_submitted_topics(self):
        for template, obj in [("edit_seminar.html", "seminar"), ("edit_talk.html", "talk")]:
            text = (ROOT / "seminars" / "create" / "templates" / template).read_text()
            self.assertIn("submitted_topics if submitted_topics is not none", text, template)
            self.assertIn("topic_dag.json(submitted_topics", text, template)
            self.assertIn("submitted_topics=None", CREATE_MAIN.read_text(), template)

    def test_js_presubmit_guard(self):
        js = (ROOT / "seminars" / "static" / "seminars.js").read_text()
        self.assertIn("#seminarform, #talkform", js)
        self.assertIn("topics_empty", js)
        self.assertIn('input[name="topics"]', js)


if __name__ == "__main__":
    unittest.main()
