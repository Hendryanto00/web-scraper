"""UI smoke checks. Run Uvicorn on port 8765 before executing this script.
Scraping responses are fixtures; this does not verify a live external integration.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:8765"
ARTIFACTS = Path(".tmp")
ARTIFACTS.mkdir(exist_ok=True)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def navigate(view):
        page.evaluate("view => location.hash = view", view)
        expect(page.locator(f'[data-view="{view}"]')).to_be_visible()
        expect(page.locator("#page-title")).to_have_text({
            "dashboard": "Dashboard", "certificates": "Data hasil scraping",
            "scraping": "Proses scraping", "history": "Riwayat scraping",
            "verification": "Verifikasi data",
            "settings": "Pengaturan", "guide": "Panduan penggunaan"
        }[view])

    assert page.goto(BASE).status == 200
    page.wait_for_selector("#server-health .green")
    expect(page.locator("#dashboard-empty")).to_be_visible()
    assert page.locator("svg.lucide").count() > 20
    page.screenshot(path=str(ARTIFACTS / "enterprise-empty.png"), full_page=True)
    sample = {
        "url": "https://example.com/data", "title": "Contoh Data",
        "text": "Contoh hasil HTML <script>window.injected = true</script>",
        "links": [{"url": "https://example.com/detail", "text": "Detail data"},
                  {"url": "javascript:alert(1)", "text": "Unsafe link fixture"}],
        "tables": [[["ID Data", "Nama", "Kategori", "Tanggal Terbit"],
                    *[[f"DATA-2026-{i:04}", f"Peserta {i}",
                       "Administrasi Perkantoran" if i % 2 else "Teknik Jaringan",
                       "18 November 2026"] for i in range(1, 26)]]]
    }
    page.route("**/scrape", lambda route: route.fulfill(json=sample))
    navigate("scraping")
    page.select_option("#auth-mode", "site_login")
    expect(page.locator("#auth-info")).to_be_visible()
    expect(page.locator("#auth-config-status")).to_contain_text("SCRAPER_LOGIN_URL")
    assert page.locator('#scrape-form input[type="password"]').count() == 0
    page.select_option("#auth-mode", "public")
    expect(page.locator("#auth-info")).to_be_hidden()
    page.click("#example")
    expect(page.locator("#url")).to_have_value("https://example.com")
    page.fill("#url", sample["url"])
    page.click("#submit")
    page.wait_for_selector("#status[data-state=success]")
    expect(page.locator("#result-title")).to_have_text(sample["title"])
    page.click("#tab-text")
    expect(page.locator("#text-result")).to_contain_text("<script>")
    assert page.evaluate("window.injected") is None
    page.click("#tab-links")
    assert page.locator("#panel-links a[href]").count() == 1
    with page.expect_download() as download:
        page.click("#download")
    assert download.value.suggested_filename == "hasil-scraping.json"
    navigate("certificates")
    expect(page.locator("#data-rows tr")).to_have_count(10)
    expect(page.locator("#data-count")).to_contain_text("25 baris")
    page.click("#next-page")
    expect(page.locator("#data-count")).to_contain_text("11")
    page.fill("#data-search", "Peserta 25")
    expect(page.locator("#data-rows tr")).to_have_count(1)
    page.click("[data-record]")
    expect(page.locator("#detail-dialog")).to_be_visible()
    page.get_by_role("button", name="Sudah diperiksa", exact=True).click()
    expect(page.locator("#data-rows")).to_contain_text("Sudah diperiksa")
    navigate("verification")
    expect(page.locator("#data-count")).to_contain_text("24 baris")
    page.select_option("#review-filter", "reviewed")
    expect(page.locator("#data-rows tr")).to_have_count(1)
    with page.expect_download() as download:
        page.click("#export-data")
    assert download.value.suggested_filename == "data-workspace.json"
    page.reload()
    page.wait_for_selector("#data-rows tr")
    expect(page.locator("#metric-records")).to_have_text("25")
    expect(page.locator("#metric-reviewed")).to_have_text("1")
    navigate("certificates")
    page.screenshot(path=str(ARTIFACTS / "enterprise-data.png"), full_page=True)
    navigate("dashboard")
    page.screenshot(path=str(ARTIFACTS / "enterprise-dashboard.png"), full_page=True)
    navigate("history")
    expect(page.locator("#history-rows tr")).to_have_count(1)
    page.click("[data-job]")
    expect(page.locator("#detail-dialog")).to_be_visible()
    page.keyboard.press("Escape")
    navigate("scraping")
    page.fill("#url", sample["url"])
    page.unroute("**/scrape")
    page.route("**/scrape", lambda route: route.fulfill(status=400, json={"detail": "Situs tujuan mengembalikan HTTP 403."}))
    page.click("#submit")
    page.wait_for_selector("#status[data-state=error]")
    expect(page.locator("#scrape-output")).to_be_visible()
    expect(page.locator("#submit")).to_be_enabled()
    navigate("history")
    page.select_option("#history-status", "error")
    expect(page.locator("#history-rows tr")).to_have_count(1)
    for width in [1024, 768, 390]:
        page.set_viewport_size({"width": width, "height": 844})
        for view in ["dashboard", "certificates", "scraping", "history", "verification", "settings", "guide"]:
            navigate(view)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), (width, view)
        print(f"PASS: responsive views at {width}px")
    navigate("certificates")
    expect(page.locator("#export-data")).to_be_visible()
    page.screenshot(path=str(ARTIFACTS / "enterprise-mobile.png"), full_page=True)
    page.click("#menu-toggle")
    expect(page.locator("#sidebar")).to_have_class("sidebar open")
    page.keyboard.press("Escape")
    expect(page.locator("#menu-toggle")).to_have_attribute("aria-expanded", "false")
    navigate("settings")
    page.fill("#operator-name", "Operator Pengujian")
    page.select_option("#page-size", "25")
    page.get_by_role("button", name="Simpan preferensi").click()
    navigate("certificates")
    expect(page.locator("#data-rows tr")).to_have_count(25)
    navigate("settings")
    page.click("#clear-session")
    page.locator("#detail-actions").get_by_role("button", name="Batal").click()
    navigate("dashboard")
    expect(page.locator("#metric-jobs")).to_have_text("2")
    navigate("settings")
    page.click("#clear-session")
    page.locator("#detail-actions").get_by_role("button", name="Hapus data sesi").click()
    navigate("dashboard")
    expect(page.locator("#metric-jobs")).to_have_text("0")
    expect(page.locator("#dashboard-empty")).to_be_visible()
    assert not errors, errors
    print("PASS: scraping success/error, safe output, table search/pagination/reviews/export, reload persistence, history, preferences and session cleanup; no JS errors.")
    browser.close()
