# PrepAI Backend

A minimal FastAPI backend for the PrepAI prototype. It exposes a working,
tested interview API that uses the same kind of sample/demo questions as the
existing frontend, and as of Phase 4.4 the frontend (`practice.html`,
`settings.html`) actually calls it. **There is no real AI evaluation
anywhere in this backend** - scores and feedback are not generated at all by
these endpoints.

## What's implemented so far

- `GET /health` - basic liveness check. Shown live on the frontend's
  Settings page ("Backend connected" / "Backend unavailable").
- `POST /api/interviews` - start an interview session. Called from
  `practice.html`'s setup screen when you click "Start Interview".
- `GET /api/interviews/{session_id}` - read a session's current state.
- `POST /api/interviews/{session_id}/answers` - submit one answer. Called
  once per question as you move past it in `practice.html`.
- `POST /api/interviews/{session_id}/complete` - mark a session completed.
  Called when you click "Finish Interview" on the last question.
- CORS restricted to `http://127.0.0.1:5500` (the frontend's Live Server origin).

## How the frontend uses this API

`prepai/js/api.js` (`window.PREP_API`) is the only place the backend URL is
hardcoded. If the backend is unreachable or rejects a request, the frontend
does **not** silently pretend a local/offline attempt came from the server:
it shows a clear message and, on the setup screen, offers a distinct
"Continue in Offline Demo Mode" button the user must click on purpose. A
completed attempt's stored `source` field (`backend` or `offline`) records
honestly which one actually happened, and the results page's wording
reflects it.

Because sessions only live in memory (see below), a question you already
submitted to the backend can't be re-submitted if you go back and edit it -
the API itself rejects that with `409`, and the frontend respects that by
locking that question's answer box instead of trying to force an update.

## What's NOT implemented yet (future phases)

- No database - sessions live in memory only (see "Sessions are not saved
  permanently" below).
- No real AI scoring or feedback - the "demo score" the frontend shows is
  the same non-AI word-count heuristic used since Phase 3, whether or not
  the backend was involved in that attempt.
- No authentication/accounts.
- No way to resume a backend session after a page refresh - if you reload
  `practice.html` mid-interview, that in-progress session (backend or
  offline) is lost, exactly as before Phase 4.4.

## Sessions are not saved permanently

Interview sessions are stored in a plain Python dictionary in memory
(`backend/storage.py`). This means **every session is lost the moment the
backend process stops or restarts.** That's expected for this phase. A real
database will be added in a later phase once the API shape is proven.

## Project files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app and route handlers. |
| `schemas.py` | Pydantic models that validate requests and shape responses. |
| `questions.py` | Small sample question bank (Technical/HR/Behavioral), mirroring `prepai/js/data.js`. |
| `storage.py` | In-memory session store and the session state machine. |
| `tests/test_api.py` | Automated pytest tests covering the endpoints below. |
| `requirements.txt` | fastapi, uvicorn, pytest, httpx. |
| `.env.example` | Placeholder for future config - nothing reads it yet. |

## Running the backend (Windows PowerShell)

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.venv\Scripts\Activate.ps1      # if you haven't already created .venv, run: python -m venv .venv
pip install -r requirements.txt
uvicorn main:app --reload
```

## Running the frontend locally (so it can reach this backend)

The backend's CORS rule only allows requests from
`http://127.0.0.1:5500` - that's VS Code's "Live Server" extension default.
With the backend running (see above):

```powershell
# in a separate terminal/window, from the frontend folder
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\prepai"
# Right-click practice.html or settings.html in VS Code and choose "Open with Live Server",
# or use any static server that serves this folder at exactly http://127.0.0.1:5500.
```

If your frontend's address bar shows a different host/port, either change
your server's port to 5500, or update `allow_origins` in `backend/main.py`
and `BASE_URL` in `prepai/js/api.js` to match - **never use a wildcard
origin** just to avoid this check.

## Running the automated tests

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.venv\Scripts\Activate.ps1
pytest tests/ -v
```

## Trying the API by hand

With the server running, open **http://127.0.0.1:8000/docs** in a browser.
This is FastAPI's built-in interactive page - you can expand any endpoint,
click "Try it out", fill in the fields, and press "Execute" to see a real
request and response.

### Example: a full walkthrough with curl

```powershell
# 1. Start an interview
curl.exe -X POST http://127.0.0.1:8000/api/interviews `
  -H "Content-Type: application/json" `
  -d '{"role":"Backend Developer","category":"hr","difficulty":"easy","question_count":2}'
# -> { "session_id": "...", "questions": [{"id":"q1", "text":"...", "answer": null}, ...], ... }

# 2. Submit an answer (replace SESSION_ID and q1 with real values from step 1)
curl.exe -X POST http://127.0.0.1:8000/api/interviews/SESSION_ID/answers `
  -H "Content-Type: application/json" `
  -d '{"question_id":"q1","answer":"My answer text"}'

# 3. Check the session state at any time
curl.exe http://127.0.0.1:8000/api/interviews/SESSION_ID

# 4. Complete the interview
curl.exe -X POST http://127.0.0.1:8000/api/interviews/SESSION_ID/complete
```

## Error responses

All errors use FastAPI's standard `{"detail": "..."}` shape, with these
status codes:

| Situation | Status |
|---|---|
| Unknown `session_id` | 404 |
| Unknown `question_id` for that session | 404 |
| Blank/whitespace-only answer | 422 |
| Invalid `category`/`difficulty`/`question_count` on creation | 422 |
| Answering a question that already has an answer | 409 |
| Submitting an answer after the session is completed | 409 |
| Completing an already-completed session | 409 |
