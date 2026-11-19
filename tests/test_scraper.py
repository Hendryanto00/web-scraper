import unittest
from email.message import Message
from io import BytesIO
from unittest.mock import patch

from fastapi import HTTPException

from app.main import ScrapeRequest, scrape
from app.scraper import MAX_BYTES, PageParser, SafeRedirectHandler, ScrapeError, scrape_url, validate_url


class ScraperTests(unittest.TestCase):
    def test_extracts_content_and_ignores_scripts(self):
        parser = PageParser("https://example.com/page")
        parser.feed('<title>Contoh &amp; Uji</title><script>rahasia</script>'
                    '<h1>Halo</h1><a href="/detail">Lihat <b>detail</b></a>'
                    '<table><tr><th>Nama</th></tr><tr><td>Ani</td></tr></table>')
        self.assertEqual(" ".join(parser.title), "Contoh & Uji")
        self.assertNotIn("rahasia", parser.text)
        self.assertEqual(parser.links, [{"url": "https://example.com/detail", "text": "Lihat detail"}])
        self.assertEqual(parser.tables, [[["Nama"], ["Ani"]]])

    def test_rejects_unsafe_urls(self):
        for url in ("file:///etc/passwd", "", "https://user:pass@example.com", "https://example.com:8000"):
            with self.subTest(url=url), self.assertRaises(ScrapeError):
                validate_url(url)
        with patch("app.scraper.socket.getaddrinfo", return_value=[(0, 0, 0, "", ("127.0.0.1", 80))]):
            with self.assertRaises(ScrapeError):
                validate_url("http://localhost")
            with self.assertRaises(ScrapeError):
                SafeRedirectHandler().redirect_request(None, None, 302, "", {}, "http://localhost")

    def response(self, content, content_type="text/html; charset=utf-8"):
        response = BytesIO(content)
        response.url = "https://example.com/final"
        response.headers = Message()
        response.headers["Content-Type"] = content_type
        return response

    @patch("app.scraper.validate_url", side_effect=lambda url: url)
    @patch("app.scraper.build_opener")
    def test_fetch_and_reject_oversized_or_non_html(self, opener, validate):
        opener.return_value.open.return_value = self.response(b"<title>Test</title><p>Isi</p>")
        result = scrape_url("https://example.com")
        self.assertEqual(result["title"], "Test")
        self.assertEqual(result["url"], "https://example.com/final")
        for content, content_type in ((b"x" * (MAX_BYTES + 1), "text/html"), (b"%PDF", "application/pdf")):
            opener.return_value.open.return_value = self.response(content, content_type)
            with self.assertRaises(ScrapeError):
                scrape_url("https://example.com")

    def test_endpoint_returns_readable_error(self):
        with self.assertRaises(HTTPException) as raised:
            scrape(ScrapeRequest(url="file:///private"))
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
