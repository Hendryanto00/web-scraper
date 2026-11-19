# Web Scraper

Dashboard lokal untuk mengambil **teks, tautan, dan tabel dari halaman web**, memeriksa hasilnya, lalu mengekspor data ke JSON atau Excel. Dibangun dengan FastAPI dan JavaScript, dengan antarmuka Bahasa Indonesia yang responsif.

Proyek ini dapat digunakan untuk menelusuri data HTML dari situs publik maupun halaman yang memerlukan login. Tidak memerlukan database untuk dijalankan.

## Fitur

- **Dashboard:** ringkasan jumlah baris, pemeriksaan, dan aktivitas scraping.
- **Tiga mode akses:** halaman publik, login otomatis melalui konfigurasi lokal, dan login manual melalui Chromium.
- **Hasil ekstraksi:** tab Tabel, Teks, Tautan, dan JSON.
- **Pengolahan tabel:** pencarian, pilihan tabel, pagination, dan pengaturan baris pertama sebagai header.
- **Pemeriksaan manual:** detail baris dengan status belum diperiksa, sudah diperiksa, atau perlu perbaikan.
- **Ekspor:** JSON hasil lengkap, JSON tabel sesuai filter, serta Excel `.xlsx` dengan pilihan kolom.
- **Riwayat sesi:** metadata 20 proses terakhir, termasuk durasi dan pesan kegagalan.
- **Panduan penggunaan:** tiga langkah awal, penjelasan mode akses, tombol salin URL contoh, dan FAQ.

## Teknologi

| Bagian | Teknologi |
| --- | --- |
| Backend dan API | Python, FastAPI, Pydantic, Uvicorn |
| Scraping publik | `urllib` dan `html.parser` dari pustaka standar Python |
| Scraping dengan login | Playwright dan Chromium |
| Antarmuka | HTML, CSS, JavaScript, ikon Lucide, font Inter lokal |
| Konfigurasi lokal | `python-dotenv` |
| Ekspor Excel | Pembuat XLSX menggunakan XML dan ZIP dari pustaka standar Python |

## Persiapan

- Python dan pip. Lingkungan pengembangan proyek ini menggunakan **Python 3.14**.
- Koneksi internet untuk mengakses situs sumber dan memasang dependensi.
- Chromium Playwright untuk mode login dan pengujian browser. Mode publik tidak memerlukan browser.

Unduh atau clone repositori ini, lalu buka terminal di folder proyek.

### Windows / PowerShell

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### Linux / macOS

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Buka **http://127.0.0.1:8000**. Biarkan terminal berjalan selama aplikasi digunakan. Tekan `Ctrl+C` untuk menghentikan server. Jika port sudah dipakai, ganti `--port 8000` menjadi `--port 8001` dan buka alamat dengan port tersebut.

Perintah berikut memakai Python virtual environment di Windows. Pada Linux/macOS, ganti `.\.venv\Scripts\python.exe` dengan `.venv/bin/python`.

## Cara penggunaan

1. Buka **Proses scraping** dan pilih mode **Publik**.
2. Masukkan URL lengkap, misalnya `https://example.com`, lalu klik **Mulai scraping**.
3. Periksa tab hasil. Situs contoh tersebut biasanya menghasilkan teks dan tautan tanpa tabel.
4. Jika sumber memiliki tabel, buka **Data hasil scraping** untuk memilih tabel, mencari nilai, dan mengatur header.
5. Buka **Verifikasi data** untuk membandingkan baris dengan sumber dan menandai hasil pemeriksaan manual.
6. Simpan hasil melalui **Unduh JSON**, **Ekspor JSON**, atau **Ekspor Excel**. Ekspor tabel mengikuti pencarian dan filter aktif di seluruh halaman tabel terpilih.

> Hanya hasil terbaru yang aktif. Riwayat menyimpan metadata proses, bukan salinan hasil lama. Unduh hasil sebelum scraping berikutnya atau menutup tab.

## Mengambil halaman yang memerlukan login

### Persiapan browser dan konfigurasi

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
Copy-Item .env.example .env
```

Pada Linux/macOS, salin konfigurasi menggunakan `cp .env.example .env`.

Isi `.env` secara lokal. Contoh berikut menggunakan domain contoh; ganti dengan alamat login dan akun situs tujuan:

```dotenv
SCRAPER_LOGIN_URL='https://accounts.example.com/login'
SCRAPER_USERNAME='your-username'
SCRAPER_PASSWORD='your-password'
```

Gunakan tanda kutip tunggal agar karakter `#` dan `$` dalam password tetap literal. Konfigurasi dibaca ulang setiap proses. Halaman login dan halaman data harus berada pada domain HTTPS yang sama.

### Pilih mode yang sesuai

| Mode | Kegunaan | Konfigurasi |
| --- | --- | --- |
| Publik | Halaman tanpa akun dengan data dalam HTML awal | Tidak memerlukan `.env` |
| Login situs | Formulir POST username/password satu tahap tanpa CAPTCHA | URL login, username, dan password di `.env` |
| Login manual + CAPTCHA | Login yang perlu diselesaikan pengguna, termasuk CAPTCHA atau langkah tambahan pada domain yang sama | Hanya URL login yang wajib; akun diisi sendiri di Chromium |

Untuk mode otomatis, selector formulir dapat disesuaikan melalui `SCRAPER_USERNAME_SELECTOR`, `SCRAPER_PASSWORD_SELECTOR`, dan `SCRAPER_SUBMIT_SELECTOR`. Mode ini mendukung token CSRF tersembunyi dalam formulir.

Dalam mode manual, Chromium terbuka di komputer yang menjalankan server. Selesaikan login, kembali ke dashboard, lalu klik **Sudah login, ambil data**. Batas waktu login adalah 5 menit dan tersedia tombol pembatalan. Mode ini memerlukan lingkungan desktop interaktif.

Setiap proses menggunakan sesi browser terisolasi yang ditutup setelah selesai. Kredensial tidak dikembalikan ke dashboard. Login SSO dan CAPTCHA pihak ketiga lintas domain belum didukung.

## Struktur proyek

```text
app/
  main.py               # FastAPI dan endpoint
  scraper.py            # Validasi URL dan ekstraksi HTML publik
  authenticated.py      # Login otomatis/manual dengan Playwright
  excel.py              # Ekspor XLSX
  templates/index.html  # Dashboard dan panduan
  static/               # CSS, JavaScript, ikon, font, dan lisensi aset
docs/
  ui-design.md          # Catatan antarmuka
tests/
  test_authenticated.py # Pengujian konfigurasi dan sesi login
  test_excel.py         # Pengujian ekspor
  test_scraper.py       # Pengujian parser dan validasi URL
  ui_smoke.py           # Pengujian alur UI dan responsivitas
.env.example            # Template konfigurasi tanpa kredensial
.gitignore
requirements.txt
README.md
```

## Pengujian

Pasang Chromium terlebih dahulu untuk menjalankan pengujian browser.

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

Untuk pengujian UI, jalankan server pada terminal pertama:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8765
```

Lalu jalankan di terminal kedua:

```powershell
.\.venv\Scripts\python.exe tests/ui_smoke.py
```

Pengujian browser memakai fixture dan respons contoh, tanpa akun situs produksi. Pemeriksaan UI mencakup navigasi, scraping berhasil/gagal, pencarian, pagination, pemeriksaan baris, ekspor, persistensi sesi, dan tampilan pada lebar 1024, 768, serta 390 piksel. Screenshot pengujian berada di `.tmp/` dan diabaikan Git.

## Batasan dan penyimpanan data

- Mode publik hanya membaca HTML awal tanpa menjalankan JavaScript. Setiap proses mengambil satu halaman dengan batas HTML 2 MB.
- PDF, pagination otomatis, penelusuran tautan otomatis, dan pemetaan kolom khusus belum tersedia.
- Tabel bersarang atau sel gabungan mungkin memerlukan penyesuaian parser.
- Hasil aktif, catatan pemeriksaan, dan preferensi disimpan melalui `sessionStorage` browser. Belum ada database, autentikasi pengguna aplikasi, atau integrasi eksternal.
- Alamat lokal/pribadi, kredensial dalam URL, dan port khusus ditolak untuk URL sumber.
- Aplikasi ditujukan untuk dijalankan pada localhost. Gunakan situs dan akun yang memberi Anda izin untuk mengambil datanya.

## File untuk repositori GitHub

Commit kode aplikasi, pengujian, dokumentasi, `requirements.txt`, `.gitignore`, dan `.env.example`. Pertahankan file lisensi aset di `app/static/`.

`.gitignore` mengecualikan konfigurasi `.env` beserta variannya, virtual environment, cache Python dan pengujian, log, screenshot sementara, pengaturan editor lokal, serta folder hasil lokal `exports/` dan `downloads/`. Template `.env.example` tetap dapat di-commit dan tidak berisi kredensial.

Simpan hasil scraping privat di folder lokal yang diabaikan atau di luar repositori. File hasil yang disimpan pada lokasi lain tidak otomatis diabaikan. Gunakan `git status --short --untracked-files=all` sebelum commit untuk memeriksa isi yang akan ditambahkan. Aturan `.gitignore` tidak menghapus file yang sudah pernah dilacak Git.
