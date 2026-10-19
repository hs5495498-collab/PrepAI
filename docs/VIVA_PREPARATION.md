# Viva Preparation Guide

44 beginner-friendly questions and concise answers, grounded in what this
repository actually contains and does. Organized by topic so you can
revise one area at a time.

## Problem statement and objectives

**1. What problem does PrepAI solve?**
It gives someone a way to practise mock interviews (technical, HR, or
behavioral questions) on their own, get a score and written feedback, and
track their progress over time - without needing a real interviewer.

**2. Who is the intended user?**
Anyone preparing for a job interview who wants structured, repeatable
practice and a record of how they're improving.

**3. What are the project's main objectives?**
Let a user run a mock interview, optionally get AI-generated questions and
AI-scored feedback, persist their results, and surface personalized
recommendations and analytics from their own history - while working
completely offline/free by default.

## Existing and proposed systems

**4. What existed before this project (in the problem space), and what's
different here?**
Generic approaches are either a real human mock interviewer (not scalable,
costs time/money) or a static list of sample questions with no feedback
loop. This project adds a persistent, per-account feedback loop (scoring,
history, recommendations) on top of a lightweight, no-build frontend.

**5. Why build the frontend as plain HTML/CSS/JS instead of a framework
like React?**
It was inherited as a Stitch-generated static prototype, and the project's
own rules (`CLAUDE.md`) explicitly forbid migrating it to a framework as a
side effect of other work - the architecture is deliberately preserved.

## Architecture

**6. What are the two main parts of this system?**
A static frontend (`prepai/`) and a FastAPI backend (`backend/`) - two
separately deployable pieces that only talk over HTTP/JSON.

**7. How does the frontend talk to the backend?**
`prepai/js/api.js` is the one file that knows the backend's URL. It wraps
`fetch()` so every call returns `{ ok, status, data }` and never throws -
`status === 0` means "couldn't reach the backend at all," distinct from a
real 4xx/5xx response.

**8. What happens if the backend is down?**
The frontend detects it (a failed health check / `status === 0`) and offers
"Continue in Offline Demo Mode" - the interview still runs, entirely in the
browser, using the fixed sample question bank.

**9. Why keep frontend and backend separate instead of one combined app?**
It matches how the project was already built, keeps the static frontend
deployable anywhere (even with no backend at all, via offline mode), and
keeps the backend a plain, independently testable JSON API.

## Frontend/backend separation details

**10. Which frontend pages actually call the backend, and which don't?**
`practice.html`, `settings.html`, `results.html`, `analytics.html`, and
`history.html` include `js/api.js` and call the backend. `index.html`
(dashboard), `achievements.html`, and `plan.html` are purely sample-data
driven and never call it.

**11. How does a page decide which JavaScript function to run?**
Each HTML file's `<body>` has a `data-page="<name>"` attribute; `app.js`
reads it on load and calls the matching function in `window.PREP_PAGES`.

## FastAPI and REST APIs

**12. What is FastAPI, in one sentence?**
A Python web framework for building HTTP APIs, with automatic request/
response validation from Python type hints (via Pydantic) and automatic
interactive docs at `/docs`.

**13. Give an example of one REST endpoint in this project and what it
does.**
`POST /api/interviews` - creates a new interview session; takes a role,
category, difficulty, and question count; returns the created session with
its generated questions.

**14. How does this project validate incoming request data?**
With Pydantic models in `schemas.py` (e.g. `InterviewCreateRequest`) - if a
request doesn't match the model's types/constraints (like `question_count`
being out of `1..15`), FastAPI automatically rejects it with a `422` before
any route code runs.

**15. What HTTP status codes does this API use, and for what?**
`200`/`201` success, `401` not authenticated, `403` missing/invalid CSRF,
`404` not found or not yours (same response for both, deliberately), `409`
a conflicting state change (duplicate answer, already completed), `422`
invalid input, `503` an AI feature is unavailable/misconfigured.

## SQLite and database design

**16. Why SQLite instead of a bigger database like PostgreSQL?**
It's a single file, needs no separate server process, and is more than
sufficient at single-user/prototype scale - appropriate for this project's
current stage. See `ARCHITECTURE.md` for what would need to change to move
to PostgreSQL later.

**17. Where is the database file, and what happens if it doesn't exist
yet?**
`backend/data/prepai.db` by default; `db.py` creates the folder and the
schema automatically on first connection if they don't exist.

**18. How does the schema avoid destroying existing data when the app
restarts or is upgraded?**
Every table is created with `CREATE TABLE IF NOT EXISTS` - running it again
against an existing database only fills in anything missing, it never
drops or rewrites an existing table.

## Keys, relationships, constraints, and indexes

**19. What is the primary key of the `questions` table, and why is it a
compound key?**
`(interview_id, id)` - a question's own ID like `q1` is only unique
*within* one interview, not across the whole database, so the primary key
has to include which interview it belongs to.

**20. What database-level constraint makes "you can't answer the same
question twice" actually enforced, not just checked in Python?**
A `UNIQUE (interview_id, question_id)` constraint on the `answers` table -
even a race between two near-simultaneous submissions can't create two
rows; the second insert fails and the code catches that and raises the
same "duplicate answer" error.

**21. Why does `interviews.user_id` have an index but no foreign key?**
SQLite can't add a foreign key to a column on an existing table without
rebuilding the whole table, and that rebuild was judged too risky to do to
a database that might hold real data. The index still makes
per-account lookups fast; ownership is enforced in application code
instead.

**22. What's an index, in simple terms, and why does `idx_questions_position`
exist?**
An index is a lookup structure the database maintains so it doesn't have to
scan every row to find what you asked for. `idx_questions_position` is a
*unique* index ensuring two questions in the same interview never share a
display position, while also speeding up ordering queries.

## Authentication and authorization

**23. What's the difference between authentication and authorization
here?**
Authentication is proving who you are (register/login, checked via the
session cookie). Authorization is deciding what you're allowed to see/do
once authenticated (the ownership check that returns 404 for someone
else's interview).

**24. How are passwords stored?**
Hashed with Argon2id (via `argon2-cffi`) - never the plain password, never
logged, never returned in any response.

**25. Why does a login with an unknown email return the exact same error
and take roughly the same time as a login with a known email but wrong
password?**
To avoid leaking which emails are registered - if unknown-email logins
failed instantly while wrong-password logins took measurably longer (due to
the hash verification), an attacker could use that timing difference to
enumerate valid accounts. The code runs a decoy hash check for the unknown-
email case specifically to equalize timing.

## Password hashing, sessions, HttpOnly cookies, CSRF, and CORS

**26. Why is a session a random token in a database table instead of a
JWT?**
No app-wide secret key to configure or ever leak, and a session can be
instantly and completely revoked just by deleting its database row -
something you can't do to a signed JWT without a separate blocklist anyway.

**27. What does `HttpOnly` mean, and which cookie here has it?**
`HttpOnly` means JavaScript cannot read the cookie's value at all - only
the browser sends it automatically with requests. `prepai_session` (the
actual session token) is `HttpOnly`; `prepai_csrf` deliberately is not,
because the frontend needs to read it to echo it back.

**28. Explain the CSRF defense used here in plain terms.**
It's the "double-submit cookie" pattern: on login, the server sets a random
CSRF token both as a readable cookie and expects it back as a request
header on every state-changing call. An attacker's forged cross-site
request would have the ambient session cookie (since cookies are sent
automatically) but could never know the CSRF cookie's value to also set a
matching header, so the forged request gets rejected with `403`.

**29. What does CORS actually control, and what's configured here?**
CORS controls which *other* origins (websites) a browser will let read the
response of a cross-origin request. This backend only allows
`http://127.0.0.1:5500` - confirmed live in Phase 12 by sending a request
with `Origin: http://evil.example.com` and observing no
`Access-Control-Allow-Origin` header came back for it.

**30. Why would a wildcard CORS origin (`*`) be a bad idea here, even if it
were simpler?**
Browsers refuse to combine a wildcard origin with `allow_credentials=True`
anyway, but more importantly it would mean any website could make
authenticated requests on a logged-in user's behalf - exactly what CORS
exists to prevent.

## Interview persistence

**31. Walk through what happens, end to end, when a user clicks "Start
Interview."**
Frontend calls `POST /api/interviews` → backend checks if AI generation is
configured (it's off by default, so it uses the fixed question bank) →
`storage.create_session` writes one `interviews` row and one `questions`
row per question, all in a single transaction → the response includes the
new session ID and its questions.

**32. What stops a half-created interview (e.g. the process crashing
mid-creation) from leaving junk data?**
`storage.create_session` wraps the interview-row insert and all its
question-row inserts in one database transaction (`with conn:`) - if
anything fails partway through, none of it is committed.

## AI question generation

**33. How does the backend decide whether to use AI-generated or fixed
questions?**
`ai_provider.is_configured()` checks two things: `AI_QUESTIONS_ENABLED`
must literally be `"true"`, and `OPENAI_API_KEY` must be set. Both must be
true, or it silently falls back to the fixed bank - no error, no cost.

**34. Does this project train or fine-tune an AI model?**
No. It makes one HTTPS request per action to OpenAI's existing Chat
Completions API and uses the response. There is no model training,
fine-tuning, or self-hosted model anywhere in this codebase.

## Structured-output validation

**35. How does the backend make sure the AI's response is actually usable
before trusting it?**
It requests a strict JSON schema (`response_format` with
`"strict": True`) so the provider's own output is constrained, and then the
backend independently re-validates every field in Python anyway (type
checks, length limits, deduplication) - the response is never passed
straight through unchecked.

## AI evaluation rubric

**36. What four dimensions make up an AI evaluation's score, and what are
their point values?**
Relevance (30), Correctness (35), Completeness (25), Clarity (10) - summing
to 100.

**37. Who actually computes the final 0-100 total score - the AI model, or
the backend?**
The backend. `evaluation_provider._parse_and_validate` sums the four
validated dimension scores itself in Python; a model-reported total is
never used, even if the model also tried to supply one.

## Score calculation

**38. Why are blank or whitespace-only answers rejected before ever being
sent to the AI evaluator?**
There's nothing to evaluate, and sending an empty answer would just waste a
request (and money, if the real provider is enabled) for a result that
should obviously be zero/low anyway - rejected client-side logic in
`evaluation_provider.evaluate_answer` before any HTTP call happens.

## Rule-based recommendations

**39. Are the "Personalized Recommendations" generated by AI?**
No - `recommendations.py` is a plain deterministic rule engine (if/else
thresholds over your own past evaluation scores). It makes no AI or network
calls at all, which is also why it still works even with both AI features
turned off.

**40. Give one concrete rule from the recommendation engine.**
If your average score in a category is below 60 (the app's existing pass
mark) across at least 3 evaluated answers, it recommends practising more
questions in that category, citing the real average as evidence.

## Analytics

**41. What does "average_score" mean in the `/api/analytics` response,
precisely?**
The mean of `total_score` across every individual evaluated *answer* you
have - not an average of each interview's own average. An interview with
more evaluated questions therefore counts proportionally more.

**42. Why is `completion_rate` ever `null` instead of `0%`?**
When you have zero total interviews, `0%` would misleadingly look like "you
attempted things and failed," when the truth is "there's no data yet" - the
code returns `null` specifically to keep those two situations visually
distinct in the UI.

## Offline mode

**43. What does "Offline Demo Mode" actually do differently from a normal
backend-backed interview?**
It runs the whole interview using only `js/data.js`'s fixed sample question
bank and browser `localStorage`, with zero network calls to the backend -
no session is ever created on the server, and the resulting attempt is
labeled `source: 'offline'` so it's never confused with a real persisted
one.

## Testing strategies

**44. How does the test suite avoid making real, paid AI requests or
touching the real database?**
Every AI-provider test injects a fake HTTP client instead of a real one
(`httpx.Client`), so no network call ever leaves the machine; and
`tests/conftest.py` points every test at its own fresh temporary SQLite
file, never `backend/data/prepai.db`. Verified in Phase 12 by running the
full 165-test suite and confirming the real database file's contents were
unaffected.

## Git and GitHub

**45. Where does this project's history live, and what was the state at
the start of Phase 12?**
`https://github.com/hs5495498-collab/PrepAI`, branch `main`. At the start
of Phase 12, local and remote `main` both pointed to the same commit
(`ebc7493`, Phase 11) with a clean working tree - verified with
`git fetch` + `git ls-remote` before any changes were made.

## Deployment and known limitations

**46. Name three things that must change before this could be deployed
publicly.**
(1) CORS origins hardcoded to `127.0.0.1:5500` must become the real
frontend domain(s); (2) `SESSION_COOKIE_SECURE` must be set to `true` under
real HTTPS; (3) there is currently no authentication rate limiting, so a
public deployment would need one added first. (See
`DEPLOYMENT_READINESS.md` for the full list.)
