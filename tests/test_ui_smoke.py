"""UI smoke tests: HTTP-level checks against a running staging server.

Needs the app booted against the local embedded-Postgres staging DB
(see README + #993), by default at http://127.0.0.1:37780.  Override
with SEMINARS_STAGING_URL.  The live-server class skips cleanly when
no server is reachable, so CI stays green without one; the template
syntax checks always run (stdlib + jinja2 only, no DB, no app import).
"""
import json
import os
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE_URL = os.environ.get("SEMINARS_STAGING_URL", "http://127.0.0.1:37780")


def request(path, data=None, timeout=15):
    url = BASE_URL + path
    body = None
    headers = {}
    if data is not None:
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.headers.get("Content-Type", ""), resp.read()
    except urllib.error.HTTPError as err:
        return err.code, err.headers.get("Content-Type", ""), err.read()


def server_up():
    try:
        status, _, _ = request("/health", timeout=3)
        return status == 200
    except Exception:
        return False


@unittest.skipUnless(server_up(), "staging server not reachable at %s" % BASE_URL)
class LiveServerTests(unittest.TestCase):
    def test_health(self):
        status, _, _ = request("/health")
        self.assertEqual(status, 200)

    def test_home_renders(self):
        status, _, body = request("/")
        self.assertEqual(status, 200)
        self.assertGreater(len(body), 1000)
        self.assertIn(b"seminar", body.lower())

    def test_talk_lists_render(self):
        for path in ["/talks", "/seminar_series", "/institutions/"]:
            with self.subTest(path=path):
                status, _, body = request(path)
                self.assertEqual(status, 200, path)
                self.assertGreater(len(body), 500, path)

    def test_pre_2020_daterange_accepted(self):
        # Regression guard for #908: pre-2020 dates must not error.
        qs = urllib.parse.urlencode(
            {"daterange": "January 1, 2015 - January 1, 2016"})
        status, _, _ = request("/past_talks?" + qs)
        self.assertEqual(status, 200)

    def test_search_api_never_500s(self):
        payload = {"query": {}, "limit": 10}
        for path in ["/api/0/search/series", "/api/0/search/talks"]:
            with self.subTest(path=path):
                status, ctype, body = request(path, data=payload)
                self.assertEqual(status, 200, path)
                self.assertEqual(json.loads(body)["code"], "success", path)

    def test_get_operator_filters_never_500(self):
        # Covers the #984 class of bug: GET filters must answer JSON
        # (200 success or 400 invalid_filter), never an HTML 500 page.
        for col_filter in ['{"$like": "%Stage%"}', '{"$ilike": "%staging%"}',
                           '{"$gte": "not-a-date"}']:
            qs = urllib.parse.urlencode({"name": col_filter})
            with self.subTest(filter=col_filter):
                status, _, body = request("/api/0/search/series?" + qs)
                self.assertIn(status, (200, 400), col_filter)
                self.assertIn(json.loads(body)["code"],
                              ("success", "invalid_filter"), col_filter)

    def test_seminar_ics_feed(self):
        status, ctype, body = request("/seminar/STAGE/ics")
        self.assertEqual(status, 200)
        self.assertIn("text/calendar", ctype)
        self.assertIn(b"VEVENT", body)

    def test_user_info_renders(self):
        status, _, _ = request("/user/info")
        self.assertEqual(status, 200)

    def test_unknown_route_404s(self):
        status, _, _ = request("/no-such-page-anywhere")
        self.assertEqual(status, 404)


class TemplateSyntaxTests(unittest.TestCase):
    def test_all_templates_parse(self):
        import jinja2

        env = jinja2.Environment()
        templates = list((ROOT / "seminars").rglob("templates/*.html")) + \
            list((ROOT / "seminars").rglob("templates/*.xml"))
        self.assertGreater(len(templates), 20, "expected to find templates")
        errors = []
        for path in sorted(templates):
            try:
                env.parse(path.read_text(encoding="utf-8"))
            except Exception as err:  # noqa: BLE001 -- collecting all failures
                errors.append(f"{path.relative_to(ROOT)}: {err}")
        self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
