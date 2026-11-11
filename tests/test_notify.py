import importlib.util
import unittest
from pathlib import Path


def load_notify():
    path = Path(__file__).resolve().parents[1] / "seminars" / "notify.py"
    spec = importlib.util.spec_from_file_location("seminars_notify_proto", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_notify = load_notify()
render_digest = _notify.render_digest
series_event = _notify.series_event
subscribers_for_event = _notify.subscribers_for_event
talk_event = _notify.talk_event


TALK = {
    "seminar_id": "STAGE", "seminar_ctr": 1, "title": "A talk",
    "speaker": "Ada", "start_time": "2030-01-01T10:00:00+00:00",
    "end_time": "2030-01-01T11:00:00+00:00", "display": True,
    "topics": ["math_NT"],
}


def user(email, confirmed=True, series=(), talks=None):
    return {
        "email": email,
        "email_confirmed": confirmed,
        "seminar_subscriptions": list(series),
        "talk_subscriptions": talks or {},
    }


class TalkEventTests(unittest.TestCase):
    def test_created(self):
        event = talk_event(None, dict(TALK))
        self.assertEqual(event["kind"], "created")
        self.assertEqual(event["seminar_ctr"], 1)

    def test_noop_returns_none(self):
        self.assertIsNone(talk_event(dict(TALK), dict(TALK)))

    def test_reschedule_kind(self):
        new = dict(TALK, start_time="2030-01-02T10:00:00+00:00")
        event = talk_event(dict(TALK), new)
        self.assertEqual(event["kind"], "rescheduled")
        self.assertIn("start_time", event["changed"])

    def test_update_kind(self):
        event = talk_event(dict(TALK), dict(TALK, title="New title"))
        self.assertEqual(event["kind"], "updated")

    def test_cancelled_on_hide(self):
        event = talk_event(dict(TALK), dict(TALK, display=False))
        self.assertEqual(event["kind"], "cancelled")


class SubscriberTests(unittest.TestCase):
    def test_series_and_talk_fanout(self):
        event = talk_event(dict(TALK), dict(TALK, title="New title"))
        users = [
            user("series@example.edu", series=["STAGE"]),
            user("talk@example.edu", talks={"STAGE": [1]}),
            user("other@example.edu", talks={"STAGE": [2]}),
            user("unconfirmed@example.edu", confirmed=False, series=["STAGE"]),
            user("elsewhere@example.edu", series=["OTHER"]),
        ]
        self.assertEqual(
            subscribers_for_event(event, users),
            ["series@example.edu", "talk@example.edu"],
        )

    def test_none_event_no_recipients(self):
        self.assertEqual(subscribers_for_event(None, [user("a@b.edu")]), [])


class DigestTests(unittest.TestCase):
    def test_digest_lines(self):
        events = [
            talk_event(None, dict(TALK)),
            series_event(None, {"shortname": "STAGE", "name": "S"}),
        ]
        digest = render_digest(events)
        self.assertIn("created STAGE talk 1", digest)
        self.assertIn("created series STAGE", digest)


if __name__ == "__main__":
    unittest.main()
