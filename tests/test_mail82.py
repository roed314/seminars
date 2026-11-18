"""Tests for issue #82 (opt-in digest sender on top of prototype #1002).

Stdlib unittest, no live DB: ``mail_digest`` is standalone (stdlib-only
at import), so it is loaded via importlib like ``tests/test_notify.py``.
Route/badge wiring is asserted via source checks (cf. test_perf.py) so
no Flask/DB import is needed.
"""
import importlib.util
import types
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIL_DIGEST = ROOT / "seminars" / "create" / "mail_digest.py"
CREATE_MAIN = ROOT / "seminars" / "create" / "main.py"
HOMEPAGE_MAIN = ROOT / "seminars" / "homepage" / "main.py"
TALK = ROOT / "seminars" / "talk.py"


def load_mail_digest():
    spec = importlib.util.spec_from_file_location("mail_digest_82", MAIL_DIGEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


md = load_mail_digest()


def user(email, confirmed=True, opt_in=True, series=(), talks=None, exclusions=None):
    return {
        "email": email,
        "email_confirmed": confirmed,
        "mail_digest_opt_in": opt_in,
        "seminar_subscriptions": list(series),
        "talk_subscriptions": talks or {},
        "talk_exclusions": exclusions or {},
    }


TALK_EVENT = {
    "scope": "talk",
    "kind": "updated",
    "seminar_id": "STAGE",
    "seminar_ctr": 1,
    "changed": ["title"],
}
SERIES_EVENT = {
    "scope": "series",
    "kind": "created",
    "seminar_id": "STAGE",
    "changed": ["name"],
}


class BuildDigestTests(unittest.TestCase):
    def test_subject_body_shape(self):
        msg = md.build_digest(user("a@example.edu", series=["STAGE"]), [TALK_EVENT])
        self.assertEqual(msg["to"], "a@example.edu")
        self.assertIn("1 update", msg["subject"])
        self.assertIn("STAGE talk 1", msg["body"])
        self.assertIn("/talk/STAGE/1/", msg["body"])
        self.assertEqual(msg["event_count"], 1)

    def test_unsubscribed_events_filtered(self):
        sub = user("a@example.edu", series=["OTHER"])
        msg = md.build_digest(sub, [TALK_EVENT, SERIES_EVENT])
        self.assertEqual(msg["event_count"], 0)
        self.assertNotIn("STAGE talk", msg["body"])

    def test_talk_subscription_and_mute(self):
        following = user("t@example.edu", talks={"STAGE": [1]})
        self.assertEqual(md.build_digest(following, [TALK_EVENT])["event_count"], 1)
        muted = user("m@example.edu", series=["STAGE"], exclusions={"STAGE": [1]})
        self.assertEqual(md.build_digest(muted, [TALK_EVENT])["event_count"], 0)

    def test_pure_no_send(self):
        self.assertFalse(hasattr(md.build_digest, "send"))


class EligibleTests(unittest.TestCase):
    def test_opt_in_confirmed_subscribed_only(self):
        users = [
            user("ok@example.edu", series=["STAGE"]),
            user("no-opt@example.edu", opt_in=False, series=["STAGE"]),
            user("unconfirmed@example.edu", confirmed=False, series=["STAGE"]),
            user("unsub@example.edu", series=["OTHER"]),
            user("talk@example.edu", talks={"STAGE": [1]}),
        ]
        self.assertEqual(
            md.eligible_recipients([TALK_EVENT], users),
            ["ok@example.edu", "talk@example.edu"],
        )

    def test_cap(self):
        users = [user("u%d@x.edu" % i, series=["STAGE"]) for i in range(60)]
        recips = md.eligible_recipients([TALK_EVENT], users, max_recipients=50)
        self.assertEqual(len(recips), 50)

    def test_empty_events_no_recipients(self):
        self.assertEqual(md.eligible_recipients([], [user("a@x.edu", series=["STAGE"])]), [])


class SendDigestTests(unittest.TestCase):
    def test_dry_run_default_sends_nothing(self):
        calls = []
        users = [user("ok@example.edu", series=["STAGE"])]
        summary = md.send_digest([TALK_EVENT], users, send_one=lambda *a: calls.append(a))
        self.assertTrue(summary["dry_run"])
        self.assertEqual(calls, [])
        self.assertEqual(summary["would_send"], ["ok@example.edu"])

    def test_explicit_dry_run_flag(self):
        import inspect

        self.assertTrue(inspect.signature(md.send_digest).parameters["dry_run"].default)

    def test_live_sends_only_eligible(self):
        calls = []
        users = [
            user("ok@example.edu", series=["STAGE"]),
            user("no-opt@example.edu", opt_in=False, series=["STAGE"]),
            user("unsub@example.edu", series=["OTHER"]),
        ]
        summary = md.send_digest(
            [TALK_EVENT], users,
            send_one=lambda to, subj, body: calls.append(to),
            dry_run=False, max_recipients=50,
        )
        self.assertFalse(summary["dry_run"])
        self.assertEqual(calls, ["ok@example.edu"])
        self.assertEqual(summary["sent"], ["ok@example.edu"])

    def test_per_run_cap(self):
        users = [user("u%d@x.edu" % i, series=["STAGE"]) for i in range(60)]
        summary = md.send_digest(
            [TALK_EVENT], users, send_one=lambda *a: None,
            dry_run=False, max_recipients=50,
        )
        self.assertLessEqual(len(summary["sent"]), 50)

    def test_rate_limit_blocks(self):
        md._SEND_LOG.clear()
        try:
            now = 1000.0
            md._SEND_LOG.extend([now - 5] * md.MAX_SENDS_PER_MINUTE)
            summary = md.send_digest(
                [TALK_EVENT], [user("a@x.edu", series=["STAGE"])],
                send_one=lambda *a: (_ for _ in ()).throw(AssertionError("must not send")),
                dry_run=False, now=now,
            )
            self.assertEqual(summary["sent"], [])
            self.assertTrue(summary.get("rate_limited"))
        finally:
            md._SEND_LOG.clear()

    def test_delivery_error_collected(self):
        def boom(to, subj, body):
            raise RuntimeError("smtp down")

        summary = md.send_digest(
            [TALK_EVENT], [user("a@x.edu", series=["STAGE"])],
            send_one=boom, dry_run=False,
        )
        self.assertEqual(summary["sent"], [])
        self.assertEqual(len(summary["errors"]), 1)


class PreviewTests(unittest.TestCase):
    def test_counts_and_sample_no_send(self):
        users = [user("ok@example.edu", series=["STAGE"]), user("u@x.edu", series=["OTHER"])]
        preview = md.preview_digest([TALK_EVENT, SERIES_EVENT], users)
        self.assertEqual(preview["event_count"], 2)
        self.assertEqual(preview["recipient_count"], 1)
        self.assertIn("STAGE talk 1", preview["sample_body"])
        self.assertFalse(preview["sent"])
        self.assertTrue(preview["dry_run"])


class ChangedBadgeTests(unittest.TestCase):
    def test_recently_changed_window(self):
        now = datetime(2030, 1, 10, tzinfo=timezone.utc)
        recent = datetime(2030, 1, 5, tzinfo=timezone.utc)
        old = datetime(2029, 12, 1, tzinfo=timezone.utc)
        self.assertTrue(md.recently_changed(recent, now=now))
        self.assertFalse(md.recently_changed(old, now=now))
        self.assertFalse(md.recently_changed(None, now=now))

    def test_mark_dicts_and_objects(self):
        now = datetime(2030, 1, 10, tzinfo=timezone.utc)
        talks = [
            {"edited_at": datetime(2030, 1, 9, tzinfo=timezone.utc)},
            {"edited_at": datetime(2029, 1, 1, tzinfo=timezone.utc)},
        ]
        self.assertEqual(md.mark_recently_changed(talks, now=now), 1)
        self.assertTrue(talks[0]["changed_badge"])
        self.assertFalse(talks[1]["changed_badge"])
        obj = types.SimpleNamespace(edited_at=datetime(2030, 1, 9, tzinfo=timezone.utc))
        md.mark_recently_changed([obj], now=now)
        self.assertTrue(obj.changed_badge)


class ConfirmTokenTests(unittest.TestCase):
    def test_roundtrip_and_reject(self):
        token = md.new_confirm_token()
        self.assertTrue(md.confirm_token_ok(token, token))
        self.assertFalse(md.confirm_token_ok("wrong", token))
        self.assertFalse(md.confirm_token_ok("", token))
        self.assertFalse(md.confirm_token_ok(None, token))


class WiringTests(unittest.TestCase):
    def test_routes_present(self):
        text = CREATE_MAIN.read_text()
        self.assertIn("manage/mail/preview", text)
        self.assertIn("manage/mail/send", text)
        self.assertIn("email_confirmed_required", text)
        self.assertIn("confirm_token_ok", text)
        self.assertIn("MAX_DIGEST_RECIPIENTS", text)
        self.assertIn("dry_run", text)

    def test_no_autosend_on_save(self):
        import ast

        tree = ast.parse(CREATE_MAIN.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.name in {
                "save_seminar", "save_talk", "save_seminar_schedule",
                "process_save_seminar", "process_save_talk",
            }:
                src = ast.get_source_segment(CREATE_MAIN.read_text(), node)
                self.assertNotIn("send_digest", src, node.name)
                self.assertNotIn("send_email", src, node.name)

    def test_badge_hook_wired(self):
        self.assertIn("mark_recently_changed", HOMEPAGE_MAIN.read_text())
        talk_text = TALK.read_text()
        self.assertIn("changed_badge", talk_text)
        self.assertIn("changed-badge", talk_text)


if __name__ == "__main__":
    unittest.main()
