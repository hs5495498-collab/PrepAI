# PrepAI Backend

A minimal FastAPI backend for the PrepAI prototype. Phase 4.3 adds a working,
tested interview API that uses the same kind of sample/demo questions as the
existing frontend. **There is no real AI evaluation anywhere in this backend
yet** - scores and feedback are not generated at all by these endpoints.

## What's implemented so far

- `GET /health` - basic liveness check (unchanged since Phase 4.1).
- `POST /api/interviews` - start an interview session.
- `GET /api/interviews/{session_id}` - read a session's current state.
- `POST /api/interviews/{session_id}/answers` - submit one answer.
- `POST /api/interviews/{session_id}/complete` - mark a session completed.
- CORS restricted to `http://127.0.0.1:5500` (the frontend's Live Server origin).

## What's NOT implemented yet (future phases)

- The frontend does **not** call this API yet - `practice.html` still uses
  only `localStorage`, exactly as in Phase 3. Wiring them together is a
  separate, later step.
- No database - sessions live in memory only (see "Sessions are not saved
  permanently" below).
- No real AI scoring or feedback.
- No authentication/accounts.

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
