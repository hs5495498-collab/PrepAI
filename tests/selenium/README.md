# Selenium end-to-end suite

Browser tests against the real `prepai/` frontend and a real FastAPI
backend - separate from `backend/tests` (API/unit tests, no browser). Do
not count tests from one suite as covering the other.

## What it does

`conftest.py` starts its own throwaway backend (`uvicorn`, pointed at an
isolated temp SQLite file - never `backend/data/prepai.db`) and its own
static file server for `prepai/` on `127.0.0.1:5500` (required exactly, by
the backend's CORS config), then drives Chrome via Selenium. If port 8000
or 5500 is already occupied (e.g. you have a dev server running), the
session aborts immediately with a clear message instead of reusing it -
stop your own server first, or just run this suite on its own.

AI question generation and AI answer evaluation are force-disabled for the
backend this suite starts (their env vars are stripped), so the suite can
never trigger a paid OpenAI call regardless of what's in `backend/.env`.

## One-time setup

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)"
backend\.venv\Scripts\python.exe -m pip install -r tests\selenium\requirements.txt
```

Requires Google Chrome installed. Selenium 4.6+'s built-in Selenium
Manager downloads a matching ChromeDriver automatically - no manual
ChromeDriver setup needed.

## Running

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)"
backend\.venv\Scripts\python.exe -m pytest tests\selenium -v --html=reports\selenium-report.html --self-contained-html
```

Runs headless by default. Set `PREPAI_SELENIUM_HEADED=1` to watch it run in
a visible Chrome window instead.

Generated reports/screenshots land in `reports\` (git-ignored) - never
committed.
