from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.scraper import ScrapeError, scrape_url
from app.authenticated import scrape_site, manual_action
from app.excel import make_excel

app = FastAPI(
    title="Scraper",
    description="Dashboard pengelolaan data",
    version="1.0.0"
)

app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home():
    return (Path(__file__).parent / "templates" / "index.html").read_text(encoding="utf-8")


@app.get("/health")
async def health():
    return {"status": "OK"}


class ScrapeRequest(BaseModel):
    url: str = Field(min_length=1, max_length=2048)
    auth_mode: Literal["public", "site_login", "manual_login"] = "public"
    manual_token: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")


class ExcelRequest(BaseModel):
    headers: list[str] = Field(min_length=1, max_length=16384)
    rows: list[list[str]] = Field(max_length=1048575)


@app.post("/export/excel")
def export_excel(payload: ExcelRequest):
    if any(len(row) != len(payload.headers) for row in payload.rows):
        raise HTTPException(status_code=400, detail="Jumlah kolom setiap baris harus sesuai header.")
    return Response(make_excel(payload.headers, payload.rows),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="data-scraping.xlsx"'})



@app.post("/scrape/manual/{token}/{action}")
def control_manual_login(token: str, action: Literal['continue', 'cancel']):
    try:
        manual_action(token, action)
        return {"status": "ok"}
    except ScrapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/scrape")
def scrape(payload: ScrapeRequest):
    try:
        if payload.auth_mode == "manual_login":
            if not payload.manual_token:
                raise ScrapeError('Sesi login manual tidak valid. Muat ulang halaman dan coba lagi.')
            return scrape_site(payload.url, manual_token=payload.manual_token)
        if payload.auth_mode == "site_login":
            return scrape_site(payload.url)
        return scrape_url(payload.url)
    except ScrapeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
