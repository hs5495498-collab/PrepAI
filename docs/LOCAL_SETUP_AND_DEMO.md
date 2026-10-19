# Local Setup and Demonstration Guide

This walks through running PrepAI entirely on your own machine: no deployment,
no public hosting, no cost. Follow it top to bottom for a first-time setup, or
jump to a section if you already have the servers running.

Project root used throughout: `C:\Users\harsh\Downloads\prepai-redesign (1)`

## 1. Open the project in PowerShell

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)"
```

Everything below assumes you start from this folder unless a step says otherwise.

## 2. Use the backend's virtual environment

The backend has its own virtual environment at `backend\.venv`, already created
and populated. Never use your system-wide Python for this project - always
call the `.venv` interpreter explicitly or activate it first.

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"

# Option A: activate it for the rest of this terminal session
.\.venv\Scripts\Activate.ps1

# Option B: call it explicitly without activating (works in any terminal)
.\.venv\Scripts\python.exe --version
```

If `backend\.venv` does not exist on your machine, create it once:

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Installing dependencies (only if something is missing)

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

This installs exactly the six packages in `requirements.txt` (`fastapi`,
`uvicorn[standard]`, `pytest`, `httpx`, `python-dotenv`, `argon2-cffi`) - no
large or unrelated package group is ever installed automatically.

## 3. Start the FastAPI backend

From the `backend` folder, with the virtual environment active (or called
explicitly):

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

- `--reload` is convenient for local development (auto-restarts on code
  changes). Leave it off if you specifically want one single, stable process
  (for example while checking which process owns port 8000).
- You should see `Uvicorn running on http://127.0.0.1:8000`.
- Leave this terminal window open - closing it stops the backend.
- Verify it's alive: open `http://127.0.0.1:8000/health` in a browser, or run
  `Invoke-RestMethod http://127.0.0.1:8000/health` in a second PowerShell
  window. Expected: `{"status":"ok"}`.
- Interactive API docs: `http://127.0.0.1:8000/docs`.

## 4. Start the static frontend server

The frontend (`prepai/`) is plain HTML/CSS/JS with no build step, but it must
be served from **exactly** `http://127.0.0.1:5500` - that's the one origin
the backend's CORS configuration allows (see `backend/main.py`). Opening the
HTML files directly with `file://` will not let them talk to the backend.

The simplest option is VS Code's **Live Server** extension:

1. Open the `prepai` folder in VS Code.
2. Right-click `index.html` → **Open with Live Server**.
3. Confirm the browser address bar shows `http://127.0.0.1:5500/...`. If Live
   Server picked a different port, change its configured port to `5500`
   (VS Code setting `liveServer.settings.port`), since the backend only
   trusts that exact origin.

Any other static file server works too, as long as it serves the `prepai`
folder at `127.0.0.1:5500`.

## 5. Open the correct URLs

| What | URL |
|---|---|
| Frontend dashboard | `http://127.0.0.1:5500/index.html` |
| Backend health check | `http://127.0.0.1:8000/health` |
| Backend interactive docs | `http://127.0.0.1:8000/docs` |

## 6. Registering, logging in, and logging out

1. Open `settings.html` from the sidebar.
2. In the **Account** section, enter an email and a password (8+ characters)
   and click **Create Account**. This registers you and logs you in in one
   step (the register endpoint also sets the session).
3. The section should now show your email and a **Log Out** button.
4. Click **Log Out** to confirm the session clears, then **Log In** again
   with the same credentials to confirm login works independently of
   registration.

Accounts are optional - nothing else on the site requires being logged in.
Logging in only changes one thing: interviews you create afterward are tied
to your account.

## 7. Creating and completing an interview

1. Open `practice.html`.
2. Choose a role, category, difficulty, and question count, then click
   **Start Interview**.
3. If the backend is reachable, this calls `POST /api/interviews` and starts
   a real, persisted session (fixed sample questions, since AI generation is
   off by default - see step 11).
4. Answer each question (typed text; the microphone/waveform UI is visual
   only, see `prepai/CLAUDE.md`) and move to the next one. Each answer is
   submitted to the backend as you move on.
5. On the last question, click **Finish Interview**. This calls
   `POST /api/interviews/{id}/complete` and takes you to `results.html`.

## 8. Viewing results

`results.html` shows the demo score (always labeled "(demo)", computed
client-side) for the attempt you just completed, plus each question and your
answer. If this attempt was submitted to the backend (not an offline-mode
attempt), each answered question also shows an **Evaluate with AI** button.

## 9. Evaluating an answer with AI (this step can cost real money - read first)

AI answer evaluation is **off by default**. Clicking "Evaluate with AI" while
it's off shows a clear "not configured" message - no cost, no error noise.

To deliberately enable it for a one-off demo:

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
copy .env.example .env
notepad .env
```

In `.env`, uncomment and fill in:

```
AI_EVALUATION_ENABLED=true
OPENAI_API_KEY=sk-...your real key...
```

Save, then **restart** `uvicorn` (stop it with Ctrl+C and run the start
command again - `.env` is only read at startup). Now clicking **Evaluate with
AI** on an answered question makes one real request to OpenAI's API and
costs a small amount (see `backend/README.md`'s "Cost note" - a fraction of a
cent per call at the default `gpt-4o-mini` model, but you are responsible for
your own OpenAI billing). Re-clicking the same button again does not re-call
the provider or re-bill - evaluation is idempotent per question.

**For the default demo, leave `AI_EVALUATION_ENABLED` and
`AI_QUESTIONS_ENABLED` unset.** Nothing else in this guide requires either
flag.

## 10. Viewing personal history

Open `history.html` while logged in. The **"Your Account History"** section
calls the backend and lists every interview you've created while logged in,
across any device, newest first. The separate **"Local Browser History (This
Device Only)"** table below it is the original sample-data/offline-attempt
table - it is unrelated and reads only this browser's `localStorage`.

## 11. Viewing analytics and recommendations

Open `analytics.html` while logged in. **"Your Account Analytics"** shows
real aggregates computed from your own evaluated answers (average/highest/
most-recent score, completion rate, category/dimension breakdowns, and a
progress chart once you have 2+ evaluated answers). **"Personalized
Recommendations"** below it is a separate, deterministic rule engine - it
makes no AI calls and works even with zero evaluations (it just tells you to
complete an interview, or to evaluate an answer, first).

If you have no evaluated answers yet, both sections show an honest "not
enough data" state rather than fabricated numbers.

## 12. Testing account isolation with two browser profiles

1. Open the app in two different browser profiles (e.g. Chrome's "Add
   person", or one normal window + one Incognito/InPrivate window) so they
   don't share cookies.
2. Register/log in as a different account in each profile.
3. Create an interview in profile A. Note its result page URL
   (`results.html?session=<id>`).
4. In profile B, try to open that same `?session=<id>` URL, or look for it in
   profile B's "Your Account History". Expected: it does not appear, and
   directly requesting it returns the same "not found" result a nonexistent
   session would - never a hint that it exists.

## 13. Testing offline demo mode

1. Stop the backend (close its terminal, or Ctrl+C).
2. In the frontend, go to `practice.html` and try to start an interview.
3. The app should detect the backend is unreachable and offer **"Continue in
   Offline Demo Mode."** Click it and confirm you can still complete a full
   interview using fixed sample questions, entirely client-side.
4. This attempt's `source` is recorded as `offline` (vs. `backend` for a
   real server-backed attempt) - visible in how `results.html` describes it.

## 14. Restarting the backend and verifying persistence

1. With the backend running, complete one interview (logged in or
   anonymous) so it's saved to `backend/data/prepai.db`.
2. Stop the backend (Ctrl+C in its terminal).
3. Start it again (same command as step 3).
4. If logged in, reopen `history.html` → "Your Account History" and confirm
   the interview you completed before the restart is still listed. If
   anonymous, you can re-fetch `GET /api/interviews/{session_id}` (e.g. via
   `/docs`) using the session ID and confirm its data is unchanged.

This confirms the SQLite database file, not an in-memory store, is the real
source of truth - restarting the process never loses data.

## 15. Stopping the servers

- **Backend**: go to its terminal window and press `Ctrl+C`. Confirm it
  exits cleanly (no further "Uvicorn running" message).
- **Frontend (Live Server)**: click "Port: 5500" in VS Code's status bar, or
  close the browser tab Live Server opened, to stop it.

## Quick reference

| Action | Command |
|---|---|
| Start backend | `cd backend; .\.venv\Scripts\python.exe -m uvicorn main:app --reload` |
| Run backend tests | `cd backend; .\.venv\Scripts\python.exe -m pytest tests/ -v` |
| Health check | `Invoke-RestMethod http://127.0.0.1:8000/health` |
| Enable AI evaluation (costs money) | edit `backend\.env`, set `AI_EVALUATION_ENABLED=true` + a real key, restart backend |
| Backend API docs | `http://127.0.0.1:8000/docs` |
