"""Authenticated extraction for a user-configured website.

Credentials remain server-side. Each extraction gets a fresh isolated browser
context; cookies are never returned, logged, or saved to disk.
"""

import os
import json
import time
from threading import Event, Lock
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from dotenv import dotenv_values
from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

from app.scraper import MAX_BYTES, ScrapeError, extract_html, validate_url

ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
TIMEOUT_MS = 30_000


@dataclass(frozen=True)
class Credentials:
    email: str = field(repr=False)
    password: str = field(repr=False)



@dataclass(frozen=True)
class LoginConfig:
    login_url: str
    username_selector: str = 'input[name="email"]'
    password_selector: str = 'input[name="password"]'
    submit_selector: str = 'button[type="submit"], input[type="submit"]'


def get_site_config(require_credentials=True):
    values = dotenv_values(ENV_PATH, interpolate=False)
    def value(name, default=''):
        return os.environ.get(name, values.get(name) or default)
    login_url = value('SCRAPER_LOGIN_URL').strip()
    if not login_url:
        raise ScrapeError('Isi SCRAPER_LOGIN_URL di .env untuk situs tujuan. Kredensial hanya dikirim ke situs yang dikonfigurasi ini.')
    validate_url(login_url)
    if urlsplit(login_url).scheme != 'https':
        raise ScrapeError('URL login harus menggunakan HTTPS.')
    credentials = Credentials(value('SCRAPER_USERNAME').strip(), value('SCRAPER_PASSWORD'))
    if require_credentials and (not credentials.email or not credentials.password):
        raise ScrapeError('Isi SCRAPER_USERNAME dan SCRAPER_PASSWORD di .env untuk situs tujuan.')
    return LoginConfig(login_url,
        value('SCRAPER_USERNAME_SELECTOR', 'input[name="username"], input[name="email"], input[type="email"], input[autocomplete="username"]'),
        value('SCRAPER_PASSWORD_SELECTOR', 'input[type="password"]'),
        value('SCRAPER_SUBMIT_SELECTOR', 'button[type="submit"], input[type="submit"]')), credentials


MANUAL_SESSIONS = {}
MANUAL_LOCK = Lock()


@dataclass
class ManualSession:
    ready: Event = field(default_factory=Event)
    cancelled: Event = field(default_factory=Event)


def manual_action(token: str, action: str):
    with MANUAL_LOCK:
        session = MANUAL_SESSIONS.get(token)
        if session is None:
            raise ScrapeError('Sesi login belum aktif atau sudah selesai.')
        if action == 'cancel':
            session.cancelled.set()
        else:
            session.ready.set()


def scrape_site(url: str, manual_token: str | None = None) -> dict:
    config, credentials = get_site_config(require_credentials=False) if manual_token else get_site_config()
    url = validate_url(url.strip())
    if urlsplit(url).netloc != urlsplit(config.login_url).netloc or urlsplit(url).scheme != 'https':
        raise ScrapeError('Domain tujuan harus sama dengan SCRAPER_LOGIN_URL di .env. Atur URL login dan kredensial untuk situs ini terlebih dahulu.')
    if urlsplit(url).path.rstrip('/') == urlsplit(config.login_url).path.rstrip('/'):
        raise ScrapeError('URL halaman data sama dengan SCRAPER_LOGIN_URL di .env. Isi SCRAPER_LOGIN_URL dengan alamat formulir login sebenarnya, bukan halaman data. Jika halaman data bisa dibuka tanpa login, pilih mode Publik tanpa login.')
    if any(part in ('logout', 'delete', 'destroy') for part in urlsplit(url).path.lower().split('/')):
        raise ScrapeError('Masukkan URL halaman data, bukan halaman logout atau penghapusan.')
    session = ManualSession() if manual_token else None
    if session:
        with MANUAL_LOCK:
            if manual_token in MANUAL_SESSIONS:
                raise ScrapeError('Sesi login sudah digunakan.')
            MANUAL_SESSIONS[manual_token] = session
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=session is None)
            try:
                with browser.new_context(accept_downloads=False, service_workers='block') as context:
                    return _scrape_with_context(context, url, credentials, config=config, manual_session=session)
            finally:
                browser.close()
    except ScrapeError:
        raise
    except PlaywrightTimeout:
        raise ScrapeError('Waktu login habis. Periksa URL login, selector formulir, kredensial, atau OTP/CAPTCHA. Login bertahap dan SSO belum didukung.') from None
    except PlaywrightError:
        raise ScrapeError('Browser gagal atau jendela login ditutup. Periksa koneksi dan instalasi Chromium, lalu coba lagi.') from None
    finally:
        if manual_token:
            with MANUAL_LOCK:
                MANUAL_SESSIONS.pop(manual_token, None)


def _fetch_response(route):
    # Inspect every redirect before allowing the browser to follow it. Native
    # browser redirects can bypass a second route interception.
    response = route.fetch(max_redirects=0, timeout=TIMEOUT_MS)
    try:
        return response.status, response.headers, response.body()
    finally:
        response.dispose()


def _scrape_with_context(context, url: str, credentials: Credentials, fetch_response=None, config: LoginConfig | None = None, manual_session: ManualSession | None = None) -> dict:
    if config is None:
        raise ScrapeError("Konfigurasi URL login wajib diberikan.")
    login_url = config.login_url
    def same_origin(address):
        try:
            parts = urlsplit(address)
            expected = urlsplit(login_url)
            return parts.scheme == 'https' and parts.hostname == expected.hostname and parts.port in (None, 443) and not parts.username and not parts.password
        except ValueError:
            return False
    def is_login_url(address):
        return urlsplit(address).path.rstrip('/') == urlsplit(login_url).path.rstrip('/')
    submission = {'url': login_url}
    fetch_response = fetch_response or _fetch_response
    login_phase = {"active": True}
    last_document = {"status": None}

    def guard(route):
        request = route.request
        # Cookies and form credentials must never follow an external origin.
        allowed = same_origin(request.url) and (
            request.method in ("GET", "HEAD")
            or (login_phase["active"] and request.method == "POST" and (manual_session is not None or request.url == submission["url"]))
        )
        if not allowed or (manual_session is None and request.resource_type in ("image", "media", "font")):
            route.abort()
            return
        try:
            validate_url(request.url)
        except ScrapeError:
            route.abort()
            return
        status, headers, body = fetch_response(route)
        if status in (301, 302, 303, 307, 308):
            destination = urljoin(request.url, headers.get("location", ""))
            if not same_origin(destination):
                route.abort()
                return
            validate_url(destination)
            if request.resource_type != "document" or request.method not in ("GET", "POST"):
                route.abort()
                return
            # A fresh document navigation is intercepted again. Never replay a
            # credential-bearing POST on a 307/308 redirect.
            destination_js = json.dumps(destination).replace("<", "\\u003c")
            redirect_headers = {"content-type": "text/html; charset=utf-8"}
            if headers.get("set-cookie"):
                redirect_headers["set-cookie"] = headers["set-cookie"]
            route.fulfill(status=200, headers=redirect_headers,
                          body=f"<!doctype html><script>location.replace({destination_js})</script>")
            return
        if request.resource_type == "document":
            last_document["status"] = status
        clean_headers = {key: value for key, value in headers.items()
                         if key.lower() not in ("content-encoding", "content-length", "transfer-encoding")}
        route.fulfill(status=status, headers=clean_headers, body=body)

    context.route("**/*", guard)
    context.route_web_socket("**/*", lambda ws: ws.close())
    page = context.new_page()
    page.set_default_timeout(TIMEOUT_MS)
    page.set_default_navigation_timeout(TIMEOUT_MS)
    page.on("dialog", lambda dialog: dialog.dismiss())
    page.on("download", lambda download: download.cancel())
    response = page.goto(login_url, wait_until="domcontentloaded")
    if not response or response.status >= 400 or not same_origin(page.url) or not is_login_url(page.url):
        raise ScrapeError("Halaman login situs tidak tersedia atau mengarah ke alamat lain.")
    if manual_session is not None:
        deadline = time.monotonic() + 300
        while not manual_session.ready.is_set():
            if manual_session.cancelled.is_set():
                raise ScrapeError('Login manual dibatalkan.')
            if time.monotonic() >= deadline:
                raise ScrapeError('Batas login manual 5 menit habis. Mulai kembali untuk mencoba lagi.')
            page.wait_for_timeout(200)
        if manual_session.cancelled.is_set():
            raise ScrapeError('Login manual dibatalkan.')
        if not same_origin(page.url) or is_login_url(page.url) or page.locator('input[type="password"]').count():
            raise ScrapeError('Login belum selesai. Selesaikan login dan CAPTCHA di browser sebelum menekan Sudah login.')
        login_phase['active'] = False
    else:
        captcha = page.locator('input[name*="captcha" i], input[id*="captcha" i], iframe[src*="recaptcha"], iframe[src*="hcaptcha"], .g-recaptcha, .h-captcha, .cf-turnstile')
        if captcha.count():
            raise ScrapeError('Halaman login memakai CAPTCHA yang harus diselesaikan pengguna. Pilih mode Login manual + CAPTCHA (browser), selesaikan CAPTCHA di browser, lalu klik Sudah login di dashboard.')
        form = page.locator('form').filter(has=page.locator(config.password_selector))
        if form.count() != 1:
            raise ScrapeError("Formulir login tidak ditemukan atau lebih dari satu. Atur SCRAPER_PASSWORD_SELECTOR di .env.")
        form_config = form.evaluate("form => ({action: form.action, method: form.method.toLowerCase()})")
        if not same_origin(form_config["action"]) or form_config["method"] != "post":
            raise ScrapeError("Tujuan formulir login tidak sesuai dengan konfigurasi situs.")
        validate_url(form_config["action"])
        submission["url"] = form_config["action"]
        form.locator(config.username_selector).first.fill(credentials.email)
        form.locator(config.password_selector).fill(credentials.password)
        # The existing hidden CSRF token is submitted by the browser itself.
        with page.expect_navigation(wait_until="domcontentloaded", timeout=TIMEOUT_MS):
            form.locator(config.submit_selector).first.click()
        login_phase["active"] = False
        if is_login_url(page.url) and page.locator('input[type="password"]').count():
            raise ScrapeError("Login situs gagal. Periksa email/password di .env. OTP atau CAPTCHA belum didukung.")
        page.wait_for_url(lambda destination: not is_login_url(destination), wait_until="domcontentloaded")
        if not same_origin(page.url):
            raise ScrapeError("Sesi login mengarah ke domain yang tidak didukung.")
    response = page.goto(url, wait_until="domcontentloaded")
    if not same_origin(page.url) or is_login_url(page.url):
        raise ScrapeError("Sesi login tidak diterima atau halaman membutuhkan autentikasi tambahan.")
    if not response or response.status >= 400:
        code = response.status if response else "tidak tersedia"
        raise ScrapeError(f"Halaman data tidak dapat dibuka (HTTP {code}). Periksa hak akses akun.")
    if response.headers.get("content-type", "").split(";")[0].strip() not in ("text/html", "application/xhtml+xml"):
        raise ScrapeError("URL admin harus mengarah ke halaman HTML.")
    try:
        page.wait_for_load_state("networkidle", timeout=5_000)
    except PlaywrightTimeout:
        pass  # Polling pages may never become idle; still try the rendered table.
    if last_document["status"] is not None and last_document["status"] >= 400:
        raise ScrapeError(f"Halaman data tidak dapat dibuka (HTTP {last_document['status']}). Periksa hak akses akun.")
    try:
        page.locator("table").first.wait_for(state="attached", timeout=5_000)
    except PlaywrightTimeout:
        pass  # A legitimate data page may contain no table.
    if not same_origin(page.url) or is_login_url(page.url) or page.locator('input[type="password"]').count():
        raise ScrapeError("Halaman masih meminta login atau autentikasi tambahan; data belum diambil.")
    html = page.content()
    if len(html.encode("utf-8")) > MAX_BYTES:
        raise ScrapeError("HTML hasil render melebihi batas ukuran 2 MB.")
    return extract_html(html, page.url)

