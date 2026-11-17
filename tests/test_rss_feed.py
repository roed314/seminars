import ast
import copy
import unittest
from datetime import datetime
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape

from email.utils import formatdate
from pytz import UTC


MAIN_PATH = Path(__file__).resolve().parents[1] / "seminars" / "utils.py"


class FakeResponse:
    def __init__(self, body, mimetype=None):
        self.body = body
        self.mimetype = mimetype


def load_rss_file():
    source = MAIN_PATH.read_text()
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "rss_file":
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            break
    else:
        raise AssertionError("rss_file not found")
    mini = ast.Module(body=[fn], type_ignores=[])
    links = []

    def fake_url_for(endpoint, _external=False, _scheme="https", **values):
        if endpoint == "show_seminar":
            url = "%s://x/seminar/%s" % (_scheme, values["shortname"])
        else:
            url = "%s://x/talk/%s/%s/" % (_scheme, values["seminar_id"], values["talkid"])
        links.append(url)
        return url

    ns = {
        "url_for": fake_url_for,
        "Response": FakeResponse,
        "xml_escape": xml_escape,
        "formatdate": formatdate,
    }
    exec(compile(mini, str(MAIN_PATH), "exec"), ns)
    return ns["rss_file"], links


def make_talk(ctr=1, **overrides):
    data = {
        "seminar_id": "STAGE",
        "seminar_ctr": ctr,
        "speaker": "Ada <b>Test</b>",
        "title": "A & B talk",
        "room": "Room 101",
        "abstract": "Fish & chips <yum>",
        "start_time": datetime(2030, 1, 2, 10, 0, tzinfo=UTC),
    }
    data.update(overrides)
    talk = type("Talk", (), {})()
    for key, val in data.items():
        setattr(talk, key, val)
    talk.show_speaker = lambda raw=False: data["speaker"]
    talk.show_title = lambda: data["title"]
    return talk


def make_seminar():
    seminar = type("Seminar", (), {})()
    seminar.name = "Staging <Series>"
    seminar.shortname = "STAGE"
    return seminar


class RssFeedTests(unittest.TestCase):
    def test_channel_and_items(self):
        rss_file, links = load_rss_file()
        resp = rss_file([make_talk(1), make_talk(2, abstract="", room="")],
                        make_seminar())
        self.assertEqual(resp.mimetype, "application/rss+xml")
        self.assertIn("<title>Staging &lt;Series&gt;</title>", resp.body)
        self.assertIn("https://x/seminar/STAGE", resp.body)
        self.assertEqual(resp.body.count("<item>"), 2)
        self.assertIn("https://x/talk/STAGE/1/", resp.body)
        self.assertIn("<pubDate>", resp.body)

    def test_escaping_and_tba(self):
        rss_file, _ = load_rss_file()
        resp = rss_file([make_talk(1, abstract="")], make_seminar())
        self.assertIn("A &amp; B talk", resp.body)
        self.assertIn("Ada &lt;b&gt;Test&lt;/b&gt;", resp.body)
        self.assertIn("Abstract: TBA", resp.body)
        self.assertNotIn("<b>Test</b>", resp.body)

    def test_empty_series(self):
        rss_file, _ = load_rss_file()
        resp = rss_file([], make_seminar())
        self.assertNotIn("<item>", resp.body)
        self.assertIn("<channel>", resp.body)


if __name__ == "__main__":
    unittest.main()
