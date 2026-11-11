"""Browser smoke tests (Playwright, local staging only).

Drives real Chromium against the staging server to prove the JS layer
works: pages boot without JS errors, the date picker accepts pre-2020
dates (#908), preference cookies are accepted with SameSite=Lax (#840),
and the seminar page exposes its ICS export.

Skipped unless SEMINARS_BROWSER_TESTS=1 with a reachable staging server
and Playwright browsers installed -- never gates CI.  Needs
``python3 -m playwright install chromium`` once.
"""
import os
import unittest
import urllib.parse
import urllib.request

from playwright.sync_api import sync_playwright


BASE_URL = os.environ.get("SEMINARS_STAGING_URL", "http://127.0.0.1:37780")
ENABLED = os.environ.get("SEMINARS_BROWSER_TESTS") == "1"


def server_up():
    try:
        with urllib.request.urlopen(BASE_URL + "/health", timeout=3) as resp:
            return resp.status == 200
    except Exception:
        return False


def browsers_installed():
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch()
            browser.close()
        return True
    except Exception:
        return False


RUN_BROWSER = ENABLED and server_up() and browsers_installed()


@unittest.skipUnless(RUN_BROWSER,
                     "browser tests need SEMINARS_BROWSER_TESTS=1, staging up, browsers installed")
class BrowserSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._pw = sync_playwright().start()
        cls.browser = cls._pw.chromium.launch()
        cls.context = cls.browser.new_context()
        # Analytics has no egress in sandboxes; block it so failure
        # assertions only cover our own origin.
        cls.context.route("**google-analytics.com**",
                          lambda route: route.abort())
        cls.context.route("**googletagmanager.com**",
                          lambda route: route.abort())
        cls.page = cls.context.new_page()
        cls.page_errors = []
        cls.failed_same_origin = []
        cls.page.on("pageerror", lambda err: cls.page_errors.append(str(err)))
        cls.page.on("requestfailed", lambda req: cls.failed_same_origin.append(req.url)
                    if req.url.startswith(BASE_URL) else None)
        # First visit sets browser_timezone and reloads mid-load (by design);
        # settle with a second visit before asserting anything.
        cls.page.goto(BASE_URL + "/", timeout=15000)
        cls.page.wait_for_timeout(1500)
        cls.page.goto(BASE_URL + "/", timeout=15000)
        cls.page.wait_for_timeout(1000)
        cls.page_errors.clear()
        cls.failed_same_origin.clear()

    @classmethod
    def tearDownClass(cls):
        cls.context.close()
        cls.browser.close()
        cls._pw.stop()

    def setUp(self):
        type(self).page_errors.clear()
        type(self).failed_same_origin.clear()

    def assertQuietLoad(self, path):
        page = type(self).page
        resp = page.goto(BASE_URL + path, timeout=15000)
        page.wait_for_timeout(1000)
        self.assertIsNotNone(resp, path)
        self.assertEqual(resp.status, 200, path)
        self.assertEqual(type(self).page_errors, [], path)
        settled = [u for u in type(self).failed_same_origin
                   if "google" not in u and "unpkg" not in u and "jsdelivr" not in u]
        self.assertEqual(settled, [], path)

    def test_home_boots_without_js_errors(self):
        self.assertQuietLoad("/")
        self.assertIn("seminar", self.page.content().lower())

    def test_browse_pages_quiet(self):
        for path in ["/talks", "/past_talks", "/seminar_series",
                     "/user/info", "/seminar/STAGE"]:
            with self.subTest(path=path):
                self.assertQuietLoad(path)

    def test_date_picker_accepts_pre_2020(self):
        # Widget-level guard for #908: the picker floor must allow 2015,
        # and a typed pre-2020 range must survive a real form submit.
        self.assertQuietLoad("/past_talks")
        floor = self.page.evaluate(
            "() => jQuery('#daterange').data('daterangepicker')"
            ".minDate.format('YYYY-MM-DD')")
        self.assertLessEqual(floor, "1970-12-31")
        self.page.click("text=more")
        self.page.fill("#daterange", "January 1, 2015 - January 1, 2016")
        with self.page.expect_navigation(timeout=15000):
            self.page.click("#more-filter-menu button")
        self.page.wait_for_timeout(800)
        # The more-filters form submits via search_* cookies + reload.
        cookies = {c["name"]: c["value"] for c in self.context.cookies()}
        self.assertIn("2015", cookies.get("search_daterange", ""), cookies)
        # The server accepted the range: quiet 200 reload, no error flash.
        flashes = self.page.eval_on_selector(
            "#flashes", "el => el.textContent.trim()")
        self.assertEqual(flashes, "")
        self.assertEqual(type(self).page_errors, [])

    def test_pre_2020_filter_round_trip(self):
        qs = urllib.parse.urlencode(
            {"daterange": "January 1, 2015 - January 1, 2016"})
        self.assertQuietLoad("/past_talks?" + qs)
        self.assertIn("2015", self.page.content())

    def test_preference_cookies_accepted_lax(self):
        self.assertQuietLoad("/past_talks")
        cookies = {c["name"]: c.get("sameSite") for c in
                   self.context.cookies()}
        for name in ["browser_timezone", "filter_topic", "filter_language",
                     "filter_more", "topics_dict"]:
            with self.subTest(cookie=name):
                self.assertIn(name, cookies, sorted(cookies))
                self.assertEqual(cookies[name], "Lax", name)

    def test_seminar_page_exposes_ics(self):
        self.assertQuietLoad("/seminar/STAGE")
        hrefs = self.page.eval_on_selector_all(
            "a[href*='/ics']", "els => els.map(e => e.getAttribute('href'))")
        self.assertTrue(any("/seminar/STAGE/ics" in h for h in hrefs), hrefs)
        resp = self.page.request.get(BASE_URL + "/seminar/STAGE/ics")
        self.assertEqual(resp.status, 200)
        self.assertIn("VEVENT", resp.text())


if __name__ == "__main__":
    unittest.main()
