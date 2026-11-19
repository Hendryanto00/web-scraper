import os
import unittest
from urllib.parse import parse_qs
from unittest.mock import patch

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

from app.authenticated import Credentials, LoginConfig, _scrape_with_context, get_site_config, scrape_site
from app.main import ScrapeRequest, scrape
from app.scraper import ScrapeError, extract_html

TEST_ORIGIN = "https://accounts.example.com"
LOGIN_URL = TEST_ORIGIN + "/admin/login"
TARGET = TEST_ORIGIN + "/admin/data"
TEST_CONFIG = LoginConfig(LOGIN_URL)
LOGIN_HTML = '''<title>Login Admin</title>
<form action="/admin/login" method="post">
<input type="hidden" name="_token" value="fixture-csrf">
<input type="email" name="email"><input type="password" name="password">
<button type="submit">Login</button></form>'''


class AuthenticationTests(unittest.TestCase):
    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_config_keeps_password_literal_and_hides_it(self, validate):
        values = {"SCRAPER_LOGIN_URL": LOGIN_URL, "SCRAPER_USERNAME": "fixture@example.com", "SCRAPER_PASSWORD": " #$secret "}
        with patch.dict(os.environ, {}, clear=True), patch("app.authenticated.dotenv_values", return_value=values):
            config, credentials = get_site_config()
            self.assertEqual(config.login_url, LOGIN_URL)
            self.assertEqual(credentials.password, " #$secret ")
            self.assertNotIn("secret", repr(credentials))

    def test_missing_credentials_does_not_launch_browser(self):
        with patch.dict(os.environ, {}, clear=True), patch("app.authenticated.dotenv_values", return_value={}), patch("app.authenticated.sync_playwright") as browser:
            with self.assertRaisesRegex(ScrapeError, "SCRAPER_LOGIN_URL"):
                scrape_site(TARGET)
            browser.assert_not_called()

    def test_login_html_is_not_reported_as_success(self):
        with self.assertRaisesRegex(ScrapeError, "halaman login"):
            extract_html(LOGIN_HTML, LOGIN_URL)

    def test_raw_browser_exception_does_not_expose_filled_password(self):
        with patch("app.authenticated.get_site_config", return_value=(TEST_CONFIG, Credentials("fixture@example.com", "fixture-secret"))), patch("app.authenticated.validate_url", side_effect=lambda url: url), patch("app.authenticated.sync_playwright", side_effect=PlaywrightError("Call log: fill fixture-secret")):
            with self.assertRaises(ScrapeError) as raised:
                scrape_site(TARGET)
            self.assertNotIn("fixture-secret", str(raised.exception))

    def test_existing_api_default_and_authenticated_dispatch(self):
        self.assertEqual(ScrapeRequest(url=TARGET).auth_mode, "public")
        with patch("app.main.scrape_site", return_value={"tables": []}) as authenticated:
            self.assertEqual(scrape(ScrapeRequest(url=TARGET, auth_mode="site_login")), {"tables": []})
            authenticated.assert_called_once_with(TARGET)


class AuthenticatedBrowserTests(unittest.TestCase):
    """Real Chromium with intercepted fixtures; no production credentials/network."""

    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch()
        except PlaywrightError as exc:
            cls.playwright.stop()
            if "Executable doesn't exist" in str(exc):
                raise unittest.SkipTest("Install Chromium: python -m playwright install chromium")
            raise

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context(service_workers="block")
        self.addCleanup(self.context.close)
        self.requests = []
        self.login_posts = []

    def serve(self, bad_password=False, deny_target=False, bad_action=False):
        def fixture(route):
            request = route.request
            self.requests.append((request.method, request.url))
            if request.url == LOGIN_URL and request.method == "GET":
                html = LOGIN_HTML.replace('action="/admin/login"', 'action="https://example.org/steal"') if bad_action else LOGIN_HTML
                return 200, {"content-type": "text/html"}, html
            elif request.url == LOGIN_URL and request.method == "POST":
                self.login_posts.append(parse_qs(request.post_data))
                if bad_password:
                    return 200, {"content-type": "text/html"}, LOGIN_HTML
                else:
                    return 302, {"location": TEST_ORIGIN + "/admin", "set-cookie": "site_session=fixture-only; Path=/; HttpOnly; Secure"}, ""
            elif request.url == TARGET:
                if deny_target:
                    return 403, {"content-type": "text/html"}, "Forbidden"
                elif "site_session=fixture-only" not in request.headers.get("cookie", ""):
                    return 302, {"location": LOGIN_URL}, ""
                else:
                    return 200, {"content-type": "text/html"}, '''<title>Pengajuan</title>
<script>
setTimeout(() => document.body.insertAdjacentHTML('beforeend', '<table><tr><th>Nama</th></tr><tr><td>Peserta fixture</td></tr></table>'), 30);
fetch('https://example.org/not-allowed').catch(() => {});
fetch('/admin/write-not-allowed', {method:'POST', body:'fixture'}).catch(() => {});
</script>'''
            elif request.url == TEST_ORIGIN + "/admin":
                return 200, {"content-type": "text/html"}, "<title>Dashboard Admin</title>"
            else:
                self.fail("Unexpected request escaped the guard: " + request.url)
        self.transport = fixture

    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_login_submits_csrf_and_extracts_rendered_table_with_session(self, validate):
        self.serve()
        result = _scrape_with_context(self.context, TARGET, Credentials("fixture@example.com", "fixture-password"), self.transport, config=TEST_CONFIG)
        self.assertEqual(result["url"], TARGET)
        self.assertEqual(result["tables"], [[["Nama"], ["Peserta fixture"]]])
        self.assertEqual(self.login_posts, [{"_token": ["fixture-csrf"], "email": ["fixture@example.com"], "password": ["fixture-password"]}])
        self.assertNotIn("fixture-password", str(result))
        self.assertFalse(any("example.org" in url or "write-not-allowed" in url for _, url in self.requests))

    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_bad_credentials_never_return_login_as_data(self, validate):
        self.serve(bad_password=True)
        with self.assertRaisesRegex(ScrapeError, "Login situs gagal"):
            _scrape_with_context(self.context, TARGET, Credentials("fixture@example.com", "wrong"), self.transport, config=TEST_CONFIG)
        self.assertNotIn(("GET", TARGET), self.requests)

    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_permission_denied_after_login_is_readable(self, validate):
        self.serve(deny_target=True)
        with self.assertRaisesRegex(ScrapeError, "HTTP 403"):
            _scrape_with_context(self.context, TARGET, Credentials("fixture@example.com", "fixture-password"), self.transport, config=TEST_CONFIG)

    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_changed_login_action_does_not_submit_credentials(self, validate):
        self.serve(bad_action=True)
        with self.assertRaisesRegex(ScrapeError, "Tujuan formulir"):
            _scrape_with_context(self.context, TARGET, Credentials("fixture@example.com", "fixture-password"), self.transport, config=TEST_CONFIG)
        self.assertEqual(self.login_posts, [])

    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_external_redirect_after_login_is_not_followed(self, validate):
        self.serve()
        fixture = self.transport
        requested_urls = []
        self.context.on("request", lambda request: requested_urls.append(request.url))

        def redirect_after_post(route):
            if route.request.method == "POST":
                return 307, {"location": "https://example.org/steal"}, ""
            return fixture(route)

        with self.assertRaises(PlaywrightError):
            _scrape_with_context(self.context, TARGET, Credentials("fixture@example.com", "fixture-password"), redirect_after_post, config=TEST_CONFIG)
        self.assertFalse(any("example.org" in url for url in requested_urls))


    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_other_domain_custom_fields_and_separate_post_action(self, validate):
        from app.authenticated import LoginConfig
        origin = 'https://accounts.example.com'
        posts = []
        def fixture(route):
            request = route.request
            if request.url == origin + '/login':
                return 200, {'content-type':'text/html'}, '<form method="post" action="/session"><input name="user_id"><input type="password" name="pass"><button type="submit">Masuk</button></form>'
            if request.url == origin + '/session':
                posts.append(parse_qs(request.post_data))
                return 302, {'location':origin + '/home'}, ''
            if request.url in (origin + '/home', origin + '/data'):
                return 200, {'content-type':'text/html'}, '<table><tr><th>ID</th></tr><tr><td>001</td></tr></table>'
            self.fail('Unexpected destination: ' + request.url)
        result = _scrape_with_context(self.context, origin + '/data', Credentials('operator', 'test-secret'), fixture,
            config=LoginConfig(origin + '/login', 'input[name="user_id"]', 'input[name="pass"]'))
        self.assertEqual(result['tables'], [[['ID'], ['001']]])
        self.assertEqual(posts, [{'user_id':['operator'], 'pass':['test-secret']}])

    def test_generic_credentials_never_sent_to_other_domain(self):
        from app.authenticated import LoginConfig, scrape_site
        with patch('app.authenticated.get_site_config', return_value=(LoginConfig('https://accounts.example.com/login'), Credentials('user', 'secret'))), patch('app.authenticated.validate_url', side_effect=lambda url:url), patch('app.authenticated.sync_playwright') as browser:
            with self.assertRaisesRegex(ScrapeError, 'Domain tujuan'):
                scrape_site('https://other.example.com/data')
            browser.assert_not_called()


    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_manual_login_keeps_captcha_images_and_session(self, validate):
        from app.authenticated import ManualSession
        session = ManualSession()
        self.serve()
        fixture = self.transport
        images = []
        def transport(route):
            if route.request.url == TEST_ORIGIN + '/captcha.png':
                images.append(route.request.url)
                return 200, {'content-type':'image/png'}, b''
            status, headers, body = fixture(route)
            if route.request.url == LOGIN_URL and route.request.method == 'GET':
                body += '<input name="captcha"><img src="/captcha.png"><script>setTimeout(()=>{document.querySelector("input[name=email]").value="manual@example.com";document.querySelector("input[name=password]").value="manual-pass";document.querySelector("form").requestSubmit()},100)</script>'
            return status, headers, body
        def on_page(page):
            page.on('framenavigated', lambda frame: session.ready.set() if frame == page.main_frame and frame.url == TEST_ORIGIN + '/admin' else None)
        self.context.on('page', on_page)
        result = _scrape_with_context(self.context, TARGET, Credentials('', ''), transport, config=TEST_CONFIG, manual_session=session)
        self.assertEqual(result['tables'], [[['Nama'], ['Peserta fixture']]])
        self.assertTrue(images)
        self.assertEqual(self.login_posts[0]['email'], ['manual@example.com'])

    @patch("app.authenticated.validate_url", side_effect=lambda url: url)
    def test_manual_cancel_stops_before_data_navigation(self, validate):
        from app.authenticated import ManualSession
        session = ManualSession()
        session.cancelled.set()
        self.serve()
        with self.assertRaisesRegex(ScrapeError, 'dibatalkan'):
            _scrape_with_context(self.context, TARGET, Credentials('', ''), self.transport, config=TEST_CONFIG, manual_session=session)
        self.assertNotIn(('GET', TARGET), self.requests)


if __name__ == "__main__":
    unittest.main()
