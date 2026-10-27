# PrepAI Postman Collection

`PrepAI.postman_collection.json` + `PrepAI.postman_environment.json` — a
verification collection for the live FastAPI backend, built directly from
the backend's own live OpenAPI schema (`GET /openapi.json`) and
`backend/auth.py`'s actual cookie/header names. No invented endpoints,
fields, or auth mechanics.

## Importing

1. Postman → **Import** → select both `.json` files in this folder.
2. Select the **PrepAI Local** environment (top-right environment picker).
3. Start the backend first (see root `README`/`backend/README.md`):
   ```powershell
   cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
   .\.venv\Scripts\python.exe -m uvicorn main:app --reload
   ```

## Running it

Run the collection **top to bottom, folder order matters** — later
requests depend on variables (`session_id`, `question_id`, `csrf_token_a`,
`session_cookie_b`, etc.) captured by earlier ones via each request's
**Tests** script. Use Postman's **Runner** for a one-click full pass, or
step through requests individually in order.

Every request that creates an account uses a freshly-generated,
disposable email (`postman-a-<timestamp>@example.com`, etc.) — it never
touches your real account. **The test password lives in the environment
file as a `secret`-type variable** (masked in the Postman UI), not hard-
coded in the collection itself, and it is a throwaway local value, not a
real credential.

## What's covered

| Folder | Verifies |
|---|---|
| 1. Health | `GET /health` |
| 2. Account & Session | Register, `GET /api/auth/me`, Logout, Login — session + CSRF cookies captured into variables after each auth call |
| 3. Interview Lifecycle | Create → retrieve → submit answer → verify it was actually persisted → complete → retrieve final results |
| 4. History/Analytics/Recommendations | `GET /api/interviews`, `GET /api/analytics`, `GET /api/recommendations` — asserts a missing evaluation is `null`, never `0` |
| 5. AI Evaluation | `POST .../evaluate` — **branches on the server's actual response** rather than presuming AI evaluation is on or off: if `200`, asserts the score is in range and the response discloses it's an estimate; if `503`, asserts the error honestly says "not configured". Either branch is a pass - see the Postman Console log for which one actually happened on your run. |
| 6. Security | Cross-account read returns `404` with no leaked fields; a state-changing request with no `X-CSRF-Token` returns `403`; an invalid `category` and an under-length password both return `422`; `GET /api/recommendations` with cookies disabled for that one request returns `401` |

## How this was verified this session

Postman's own CLI runner (`npx newman run ...`) was blocked by this
environment's auto-mode sandbox (external-code execution). Every one of
the 21 requests' exact method/URL/body/headers was instead replayed
manually via `curl` against the real running backend, confirming the
live status code and response body matched every assertion in this
collection's Tests scripts, byte-for-byte in most cases. See the session's
evidence report (`docs/TEST_EVIDENCE_<date>.md`) for the full transcript.
The two disposable test accounts and one test interview that curl pass
created were deleted again afterward (see that report) - this collection
itself, when you run it, will create its own fresh disposable accounts.

## Safety notes

- Never add a real API key, password, or session cookie value directly
  into the collection JSON - use the environment's `secret`-type variable
  facility instead (already set up for the test password).
- This collection never deletes or overwrites any existing account or
  interview - every write it makes is to a newly-registered test account.
