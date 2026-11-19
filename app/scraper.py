"""Fetch a public HTML page and extract its readable content."""

import ipaddress
import socket
import ssl
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_BYTES = 2 * 1024 * 1024


class ScrapeError(ValueError):
    pass


def validate_url(url: str) -> str:
    url = url.strip()
    try:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ScrapeError("URL harus lengkap dan menggunakan http:// atau https://.")
        if parts.username or parts.password or parts.port not in (None, 80, 443):
            raise ScrapeError("URL tidak boleh berisi kredensial atau port khusus.")
        addresses = socket.getaddrinfo(parts.hostname, parts.port or (443 if parts.scheme == "https" else 80), type=socket.SOCK_STREAM)
        if not addresses or any(not ipaddress.ip_address(item[4][0]).is_global for item in addresses):
            raise ScrapeError("Gunakan URL situs publik; alamat lokal/pribadi tidak didukung.")
    except (ValueError, OSError) as exc:
        if isinstance(exc, ScrapeError):
            raise
        raise ScrapeError("URL tidak valid atau nama domain tidak dapat ditemukan.") from exc
    return url


class SafeRedirectHandler(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, validate_url(newurl))


class PageParser(HTMLParser):
    def __init__(self, url):
        super().__init__(convert_charrefs=True)
        self.url = url
        self.title = []
        self.text = []
        self.links = []
        self.tables = []
        self.hidden = []
        self.in_title = False
        self.link = None
        self.table = None
        self.row = None
        self.cell = None
        self.has_password_field = False

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("type", "").lower() == "password":
            self.has_password_field = True
        if tag in ("script", "style", "noscript", "template"):
            self.hidden.append(tag)
        if self.hidden:
            return
        if tag == "title":
            self.in_title = True
        elif tag == "a":
            href = urljoin(self.url, attrs.get("href", ""))
            self.link = {"url": href, "text": ""} if attrs.get("href") and urlsplit(href).scheme in ("http", "https") else None
        elif tag == "table" and self.table is None:
            self.table = []
        elif tag == "tr" and self.table is not None:
            self.row = []
        elif tag in ("td", "th") and self.row is not None:
            self.cell = []

    def handle_endtag(self, tag):
        if self.hidden:
            if tag == self.hidden[-1]:
                self.hidden.pop()
            return
        if tag == "title":
            self.in_title = False
        elif tag == "a" and self.link is not None:
            self.link["text"] = " ".join(self.link["text"].split())
            self.links.append(self.link)
            self.link = None
        elif tag in ("td", "th") and self.cell is not None:
            self.row.append(" ".join(" ".join(self.cell).split()))
            self.cell = None
        elif tag == "tr" and self.row is not None:
            if self.row:
                self.table.append(self.row)
            self.row = None
        elif tag == "table" and self.table is not None:
            if self.table:
                self.tables.append(self.table)
            self.table = None

    def handle_data(self, data):
        if self.hidden or not data.strip():
            return
        if self.in_title:
            self.title.append(data.strip())
        else:
            self.text.append(data.strip())
        if self.link is not None:
            self.link["text"] += data + " "
        if self.cell is not None:
            self.cell.append(data)


def extract_html(html: str, url: str) -> dict:
    parser = PageParser(url)
    parser.feed(html)
    title = " ".join(parser.title)
    if parser.has_password_field and ("login" in urlsplit(url).path.lower() or "login" in title.lower()):
        raise ScrapeError("Situs mengarahkan ke halaman login. Pilih mode Login situs atau Login manual dan konfigurasi URL login di .env.")
    return {"url": url, "title": title, "text": "\n".join(parser.text), "links": parser.links, "tables": parser.tables}


def scrape_url(url: str) -> dict:
    url = validate_url(url)
    opener = build_opener(ProxyHandler({}), SafeRedirectHandler())
    request = Request(url, headers={"User-Agent": "WebScraper/1.0", "Accept": "text/html,application/xhtml+xml"})
    try:
        with opener.open(request, timeout=20) as response:
            if response.headers.get_content_type() not in ("text/html", "application/xhtml+xml"):
                raise ScrapeError("URL harus mengarah ke halaman HTML, bukan PDF atau berkas lain.")
            content = response.read(MAX_BYTES + 1)
            if len(content) > MAX_BYTES:
                raise ScrapeError("Halaman melebihi batas ukuran 2 MB.")
            encoding = response.headers.get_content_charset() or "utf-8"
            try:
                html = content.decode(encoding, errors="replace")
            except LookupError:
                html = content.decode("utf-8", errors="replace")
            return extract_html(html, response.url)
    except HTTPError as exc:
        raise ScrapeError(f"Situs tujuan mengembalikan HTTP {exc.code}.") from exc
    except URLError as exc:
        if isinstance(exc.reason, ssl.SSLCertVerificationError):
            raise ScrapeError("Sertifikat HTTPS gagal diverifikasi. Periksa sertifikat CA Python atau jaringan Anda.") from exc
        raise ScrapeError("Halaman tidak dapat diakses atau waktu tunggu habis.") from exc
    except (TimeoutError, OSError) as exc:
        raise ScrapeError("Halaman tidak dapat diakses atau waktu tunggu habis.") from exc
