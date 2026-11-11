import ast
import copy
import hashlib
import re
import types
import unittest
from datetime import datetime
from email.utils import formatdate, parsedate_to_datetime
from io import BytesIO
from pathlib import Path

import pytz
from icalendar import Calendar, Event
from pytz import UTC

TALK_PATH = Path(__file__).resolve().parents[1] / "seminars" / "talk.py"
UTILS_PATH = Path(__file__).resolve().parents[1] / "seminars" / "utils.py"


def fake_url_for(endpoint, _external=False, _scheme="https", **values):
    return "%s://example.com/%s" % (_scheme, endpoint)


def load_event():
    source = TALK_PATH.read_text()
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "event":
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            break
    else:
        raise AssertionError("event not found")
    mini = ast.Module(body=[fn], type_ignores=[])
    ns = {
        "url_for": fake_url_for,
        "Event": Event,
        "re": re,
        "pytz": pytz,
        "datetime": datetime,
        "adapt_datetime": lambda t, newtz=None: t.astimezone(newtz) if newtz else t,
        "topdomain": lambda: "example.com",
    }
    exec(compile(mini, str(TALK_PATH), "exec"), ns)
    return ns["event"]


class FakeResp:
    def __init__(self, body=None, status=None, mimetype=None):
        self.body = body
        self.status_code = status if status is not None else 200
        self.mimetype = mimetype
        self.headers = {}


def load_ics_file(headers=None):
    source = UTILS_PATH.read_text()
    module = ast.parse(source)
    for node in ast.walk(module):
        if isinstance(node, ast.FunctionDef) and node.name == "ics_file":
            fn = copy.deepcopy(node)
            fn.decorator_list = []
            break
    else:
        raise AssertionError("ics_file not found")
    mini = ast.Module(body=[fn], type_ignores=[])
    captured = {}

    def fake_send_file(bIO, **kwds):
        captured.update(kwds)
        captured["data"] = bIO.read()
        return FakeResp()

    ns = {
        "Calendar": Calendar,
        "BytesIO": BytesIO,
        "hashlib": hashlib,
        "request": types.SimpleNamespace(headers=dict(headers or {})),
        "current_user": object(),
        "send_file": fake_send_file,
        "Response": FakeResp,
        "formatdate": formatdate,
        "parsedate_to_datetime": parsedate_to_datetime,
        "pytz": pytz,
        "topdomain": lambda: "example.com",
    }
    exec(compile(mini, str(UTILS_PATH), "exec"), ns)
    return ns["ics_file"], captured


START = datetime(2030, 1, 2, 10, 0, tzinfo=UTC)
END = datetime(2030, 1, 2, 11, 0, tzinfo=UTC)
EDITED = datetime(2030, 1, 3, 12, 0, tzinfo=UTC)


def make_talk(ctr=1, edited=EDITED, **overrides):
    talk = types.SimpleNamespace(
        seminar_id="STAGE",
        seminar_ctr=ctr,
        speaker="Ada",
        title="Some title",
        live_link="",
        stream_link="",
        room="",
        abstract="",
        comments="",
        access_control=0,
        access_hint="",
        start_time=START,
        end_time=END,
        edited_at=edited,
        seminar=types.SimpleNamespace(name="Series"),
    )
    for key, val in overrides.items():
        setattr(talk, key, val)
    talk.show_speaker = lambda raw=False: "Ada"
    talk.show_live_link = lambda user=None, raw=False: ""
    talk.show_stream_link = lambda user=None, raw=False: ""
    talk.event = lambda user=None: EVENT_FN(talk, user)
    return talk


EVENT_FN = load_event()


class IcsEventTests(unittest.TestCase):
    def test_dtstamp_stable_and_uses_edited_at(self):
        talk = make_talk()
        ev1 = EVENT_FN(talk, None)
        ev2 = EVENT_FN(talk, None)
        self.assertEqual(ev1.decoded("DTSTAMP"), EDITED)
        self.assertEqual(ev2.decoded("DTSTAMP"), EDITED)

    def test_dtstamp_falls_back_to_start_time(self):
        talk = make_talk(edited=None)
        ev = EVENT_FN(talk, None)
        self.assertEqual(ev.decoded("DTSTAMP"), START)

    def test_uid_sequence_last_modified(self):
        talk = make_talk()
        ev = EVENT_FN(talk, None)
        self.assertEqual(ev.decoded("UID"), "STAGE/1@example.com")
        self.assertEqual(ev.decoded("SEQUENCE"), 0)
        self.assertEqual(ev.decoded("LAST-MODIFIED"), EDITED)

    def test_no_last_modified_without_edited_at(self):
        talk = make_talk(edited=None)
        ev = EVENT_FN(talk, None)
        self.assertNotIn("LAST-MODIFIED", ev)


class IcsFileTests(unittest.TestCase):
    def test_headers_and_body(self):
        ics_file, captured = load_ics_file()
        resp = ics_file([make_talk(1), make_talk(2)], "x.ics", user=object())
        data = captured["data"]
        self.assertFalse(captured["as_attachment"])
        self.assertEqual(captured["mimetype"], "text/calendar")
        self.assertEqual(resp.headers["Content-Type"], "text/calendar; charset=utf-8")
        self.assertEqual(resp.headers["ETag"], '"%s"' % hashlib.sha256(data).hexdigest())
        self.assertEqual(resp.headers["Last-Modified"], formatdate(EDITED.timestamp(), usegmt=True))
        self.assertEqual(resp.headers["Cache-Control"], "public, max-age=3600")
        self.assertIn(b"METHOD:PUBLISH", data)
        self.assertIn(b"UID:STAGE/1@example.com", data)

    def test_bytes_deterministic(self):
        ics_file, captured1 = load_ics_file()
        ics_file([make_talk(1)], "x.ics", user=object())
        ics_file2, captured2 = load_ics_file()
        ics_file2([make_talk(1)], "x.ics", user=object())
        self.assertEqual(captured1["data"], captured2["data"])

    def test_if_none_match_304(self):
        ics_file, captured = load_ics_file()
        resp = ics_file([make_talk(1)], "x.ics", user=object())
        etag = resp.headers["ETag"]
        ics_file_cond, _ = load_ics_file(headers={"If-None-Match": etag})
        resp304 = ics_file_cond([make_talk(1)], "x.ics", user=object())
        self.assertEqual(resp304.status_code, 304)
        self.assertEqual(resp304.headers["ETag"], etag)

    def test_if_modified_since_304(self):
        ics_file, captured = load_ics_file()
        resp = ics_file([make_talk(1)], "x.ics", user=object())
        lm = resp.headers["Last-Modified"]
        ics_file_fresh, _ = load_ics_file(headers={"If-Modified-Since": lm})
        self.assertEqual(ics_file_fresh([make_talk(1)], "x.ics", user=object()).status_code, 304)
        ics_file_old, _ = load_ics_file(headers={"If-Modified-Since": formatdate(0, usegmt=True)})
        self.assertEqual(ics_file_old([make_talk(1)], "x.ics", user=object()).status_code, 200)

    def test_no_last_modified_without_edited_at(self):
        ics_file, captured = load_ics_file(headers={"If-Modified-Since": formatdate(EDITED.timestamp(), usegmt=True)})
        resp = ics_file([make_talk(1, edited=None)], "x.ics", user=object())
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("Last-Modified", resp.headers)
        self.assertIn("ETag", resp.headers)


if __name__ == "__main__":
    unittest.main()
