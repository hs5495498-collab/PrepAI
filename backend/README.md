# PrepAI Backend

A minimal FastAPI backend for the PrepAI prototype. It exposes a working,
tested interview API, and the frontend (`practice.html`, `settings.html`,
`results.html`, `analytics.html`) actually calls it (since Phase 4.4). Two
independent AI features exist, both OFF by default and controlled by
separate flags: **question generation** (Phase 5) and **answer
evaluation/scoring** (Phase 8). Enabling one never enables the other. Any
score an answer receives - from either feature's path - is always an
AI-generated *estimate for practice purposes*, never an objective or
official measurement; the evaluation response even says so in its own
`note` field. **Personalized recommendations** (Phase 9) are a third,
separate thing again: a deterministic, rule-based engine that reuses
already-persisted evaluation data - it makes no AI calls of its own at all.
**Personal history and analytics** (Phase 10) expose that same persisted
data directly - also no AI calls, just database queries and arithmetic.

## What's implemented so far

- `GET /health` - basic liveness check. Shown live on the frontend's
  Settings page ("Backend connected" / "Backend unavailable").
- `POST /api/interviews` - start an interview session. Called from
  `practice.html`'s setup screen when you click "Start Interview". Its
  questions come from AI generation if configured (see below), otherwise
  from the existing fixed sample bank - the response's `question_source`
  field (`"ai"` or `"fixed"`) always says which one honestly.
- `GET /api/interviews/{session_id}` - read a session's current state.
  Since Phase 10, each question's response also includes its persisted
  `evaluation` (or `null` if that question was never evaluated).
- `GET /api/interviews` - a paginated list of your own account's
  interviews, newest first (Phase 10, see below).
- `POST /api/interviews/{session_id}/answers` - submit one answer. Called
  once per question as you move past it in `practice.html`.
- `POST /api/interviews/{session_id}/complete` - mark a session completed.
  Called when you click "Finish Interview" on the last question.
- `POST /api/auth/register`, `POST /api/auth/login`, `POST /api/auth/logout`,
  `GET /api/auth/me` - account creation and sessions (Phase 7, see below).
- `POST /api/interviews/{session_id}/questions/{question_id}/evaluate` -
  score one already-submitted answer with AI feedback (Phase 8, see below).
- `GET /api/recommendations` - a short, personalized list of what to
  practise next, built from your own evaluated answers (Phase 9, see below).
- `GET /api/analytics` - your own account's aggregate stats: average/
  highest/most-recent score, completion rate, category/dimension
  breakdowns, and a score-over-time series (Phase 10, see below).
- CORS restricted to `http://127.0.0.1:5500` (the frontend's Live Server
  origin), with `allow_credentials=True` so the session cookie works.

## AI question generation (Phase 5)

`ai_provider.py` is a self-contained service, kept separate from the route
handlers in `main.py`. It calls OpenAI's Chat Completions API with a strict
JSON schema so the response is always a plain list of question strings -
never answers, scores, or anything else.

**It is OFF by default**, and needs two separate environment variables set
before it will ever make a real (paid) request:

```
AI_QUESTIONS_ENABLED=true
OPENAI_API_KEY=sk-...your real key...
OPENAI_MODEL=gpt-4o-mini   # optional, this is already the default
```

Requiring *both* a key and an explicit `true` flag is deliberate: a leftover
`OPENAI_API_KEY` in your environment from some other project can never
silently make PrepAI start spending money. If either is missing, every
interview uses the existing fixed question bank - exactly like Phase 4.4,
with no error and no cost.

**If AI generation is enabled but the request fails** (timeout, invalid/
expired key, rate limit, outage, or a response that fails validation),
`POST /api/interviews` returns a clear `503` error - it does **not**
silently hand back fixed questions and pretend they came from AI. On the
frontend, this shows as a plain error message plus the same "Continue in
Offline Demo Mode" button Phase 4.4 already built for "backend unreachable"
- clicking it is an explicit choice to proceed with fixed demo questions
instead.

### Creating your own `.env` (never commit this file)

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
copy .env.example .env
notepad .env   # fill in OPENAI_API_KEY and set AI_QUESTIONS_ENABLED=true
```

`.env` is already excluded by the repository's `.gitignore`. The backend
loads it automatically at startup (via `python-dotenv`) - just restart
`uvicorn` after editing it.

### Cost note

OpenAI's `gpt-4o-mini` pricing (checked via third-party trackers in Oct
2026, since OpenAI's own pricing page blocked automated fetching - verify
at platform.openai.com/pricing before relying on this) is roughly
$0.15 / $0.60 per million input/output tokens. A single interview-question
request is a few hundred tokens each way, so the estimated cost is a small
fraction of a cent per interview - but this is an estimate, not a quote,
and you are responsible for your own OpenAI account's billing.

## AI answer evaluation (Phase 8)

`evaluation_provider.py` scores one already-submitted answer and gives
feedback. It is completely separate from `ai_provider.py` (question
generation) - different file, different feature flag, different endpoint.
**Enabling question generation never enables evaluation, and vice versa.**

### How evaluation differs from question generation

| | Question generation (Phase 5) | Answer evaluation (Phase 8) |
|---|---|---|
| Flag | `AI_QUESTIONS_ENABLED` | `AI_EVALUATION_ENABLED` |
| When it runs | Once, when you click "Start Interview" | On demand, when you click "Evaluate with AI" on the results page |
| What it sends the provider | Role/category/difficulty/count | Role/category/difficulty + the one question + your one answer |
| What it returns | A list of question strings | A score breakdown + written feedback for one answer |

### Enabling it

```
AI_EVALUATION_ENABLED=true
```

in your `.env` (reuses the same `OPENAI_API_KEY`/`OPENAI_MODEL` as question
generation - no separate key needed). Leaving it unset (the default) means
every evaluation request gets a clear `503 AI answer evaluation is not
configured on this server.` - never a silent failure, never a fake score.

### The scoring rubric

Four dimensions, summing to 100 - the model returns each dimension
separately, and **the backend adds them up itself** (`evaluation_provider.py`
's `_parse_and_validate`), it never trusts a model-reported total:

| Dimension | Points | What it measures |
|---|---|---|
| Relevance | 30 | Does the answer actually address the question asked |
| Correctness | 35 | Technical/factual accuracy, or soundness of reasoning |
| Completeness | 25 | Covers the important points without leaving out key parts |
| Clarity | 10 | Organized, easy to follow |

For a **technical** question the prompt asks the model to weigh accuracy
heavily and call out missing concepts. For **HR/behavioral** questions the
prompt explicitly tells the model there is no single correct technical
answer and to instead judge relevance, specificity of the example,
structure, reflection, and the candidate's own contribution - a technical
correctness test is never applied to that kind of answer. The model is
told not to reward length or impressive vocabulary over substance, and
that a blank/off-topic/nonsensical answer must score very low - blank
answers are additionally rejected before ever reaching the model at all
(see below).

The response always includes a `note` field stating the score is an
AI-generated estimate for practice, not an objective or official
assessment - this is written into the API response itself, not just this
document.

### What gets sent to the provider, and what doesn't

Only the interview's role/category/difficulty, the one question's text,
and your one answer for that question are sent - nothing else. Your email,
other answers, other questions, session tokens, and password hashes are
never included. **If you enable live evaluation, the specific answer text
you submit for that question is sent to OpenAI** for that one request -
this is true any time you click "Evaluate with AI" while the feature is
configured; it is not sent anywhere when the feature is off (the default).

### Validation and failure handling

Every field in the model's response is checked before it's trusted: each
dimension score must be an integer within its documented range (out of
range → rejected, not clamped), `strengths`/`weaknesses`/`suggestions` must
be non-empty lists of non-empty strings, and the three text fields must be
non-empty. A blank or whitespace-only answer is rejected before any request
is sent - there is nothing to evaluate. Any failure (timeout, bad
credentials, rate limit, provider outage, or output that fails validation)
returns a clear `503` and **does not save anything** - a failed evaluation
can never be mistaken for a low-scoring real one, and there is no automatic
retry (which would mean a second charge for one click).

### Idempotency - re-evaluating does not double-call or double-charge

`POST .../evaluate` is idempotent per question: the `evaluations` table has
a `UNIQUE (interview_id, question_id)` constraint, and the route checks for
an existing row first. Calling it again for an already-evaluated question
returns the **same stored result** - the provider is never called twice
for the same question, and no duplicate row is ever created. There is
currently no "re-evaluate" or "regenerate" action; the first successful
evaluation is permanent for that question.

## Personalized recommendations (Phase 9)

`GET /api/recommendations` returns a short, ordered list of what to
practise next, built entirely from **your own account's** completed
interviews and evaluated answers. It requires being logged in (there is no
anonymous equivalent - recommendations are inherently tied to an account's
history). This is a **plain, deterministic rule engine** (`recommendations.py`)
- not machine learning, and it makes **no AI/network calls of its own at
all**, so there is no cost and no provider configuration needed for this
endpoint to work, even with both AI features disabled.

### What data it uses

Only the authenticated account's own `evaluations` rows (joined with their
interview's `category`/`difficulty`) and its count of completed interviews.
`storage.get_user_recommendation_data()` filters by `user_id` at the SQL
level - anonymous interviews (`user_id IS NULL`) and other accounts'
interviews are never included, because the query never sees them in the
first place. Only the most recent 10 evaluations are considered for
trend/consistency checks (`RECENT_WINDOW` in `recommendations.py`) - recent
enough to reflect current performance without old history diluting it.

### Rules and thresholds (all in `recommendations.py`, each documented inline)

| Rule | Threshold | Why |
|---|---|---|
| No completed interviews | `completed_interviews == 0` | Nothing to base anything on - returns one generic "complete your first interview" suggestion. |
| Interviews but no evaluations | `len(evaluations) == 0` | Returns one generic "try Evaluate with AI" suggestion, distinct wording from the above. |
| Weak category | Average score in a category < 60 | Reuses the app's own existing pass/fail line (`P.passMark` in `data.js`) instead of inventing a second number. |
| Strong category -> harder difficulty | Average score in a category >= 85, at a difficulty below "hard" | Comfortably above the pass mark - only reached by consistent strength. |
| Weak rubric dimension | A dimension's average < 60% of its own max | Same ratio as the category threshold, applied per-dimension (e.g. correctness < 21/35). |
| Inconsistent category | Same-category score range (max-min) >= 40 | Large enough that it can't be ordinary noise between similar answers. |
| "Enough data" to call something a trend | >= 3 evaluated answers | Below 3, one unusually good or bad answer can swing an average entirely. |

A category or dimension with **fewer than 3** samples can still produce a
recommendation if it's clearly weak, but it is marked `evidence_level:
"limited"` and given `priority: "medium"` instead of `"high"` - the
difference between "weak" and "not enough evidence yet" is explicit in the
response, never silently merged. A category that has **zero** evaluations
is never mentioned at all - the engine never claims poor performance in
something the user hasn't actually attempted.

Weak and "suggest harder difficulty" recommendations for the *same*
category can never both appear (one requires average < 60, the other >= 85
- mutually exclusive by construction). At most 4 recommendations are
returned (`MAX_RECOMMENDATIONS`), sorted by priority (`high` → `medium` →
`low`) and then by a fixed key order, so the same underlying data always
produces the exact same list in the exact same order.

### Optional AI-generated wording - not implemented this phase

The recommendation text is already written in plain language by this
module directly (not templated robotic output), so there was no clear need
for an additional AI-wording layer this phase, and adding one would have
meant a new provider module, a new flag, and new tests for something
optional. This is documented here as deliberate future work, not an
oversight - if added later, it must (per the same pattern as question
generation/evaluation) be its own explicit flag, must never be required
for the core recommendations to work, and must never be allowed to invent
or override the real underlying scores.

### Privacy

The response never includes another account's data, password hashes,
session tokens, or CSRF tokens - it contains only the recommendation text,
priority, evidence strings built from the account's own real scores, and
two small counters (`completed_interviews`, `evaluated_answers`). No answer
text or personal data is sent anywhere - this endpoint doesn't call any
external service.

## Personal history and analytics (Phase 10)

Both endpoints below require being logged in and only ever return the
authenticated account's own data - there is no anonymous equivalent, and
anonymous interviews (`user_id IS NULL`) are never attributed to any
account, never counted in any account's totals, and never returned by
either endpoint. Ownership is enforced by a SQL `WHERE user_id = ?` on
every query (`storage.list_user_interviews`,
`storage.get_user_recommendation_data`) - never filtered in Python after
the fact. Neither endpoint calls an AI provider; both are plain database
queries plus arithmetic.

### `GET /api/interviews` - interview history

Returns `{interviews: [...], total, limit, offset}`, newest first
(`ORDER BY created_at DESC, id DESC` - the `id` tiebreak keeps ordering
fully deterministic even when two interviews share the same timestamp).
Query parameters:

| Parameter | Default | Notes |
|---|---|---|
| `limit` | 20 | Clamped to the range 1-100 server-side regardless of what's requested. |
| `offset` | 0 | Clamped to >= 0. |

Each item includes `session_id`, `role`, `category`, `difficulty`,
`status`, `question_count`, `answered_count`, `evaluated_count`,
`average_score`, `created_at`, `completed_at`. `average_score` is the mean
of `total_score` across *that interview's own* evaluated questions - it is
`null` (never `0`) when that interview has zero evaluated questions, so an
unevaluated interview is never mistaken for a scored-zero one. This is a
single SQL statement per request (correlated subqueries for the three
counts, not a separate round trip per interview), so listing a page of
history is never an N+1 query pattern.

### `GET /api/interviews/{session_id}` - interview detail (existing endpoint, extended)

This route already existed (Phase 4.3) and is reused, not duplicated. As
of Phase 10, each question in the response additionally carries an
`evaluation` field - the same data `POST .../evaluate` returns, minus the
redundant `session_id`/`question_id`, or `null` if that question was never
evaluated. This is purely additive: the field was added with a default of
`null`, so every caller that existed before Phase 10 (`practice.html`'s
live session) is completely unaffected. Ownership uses the exact same
`_check_ownership` check as every other interview route - another
account's session ID returns the same `404 Interview session not found`
a nonexistent ID would, never revealing that it exists.

### `GET /api/analytics` - account-wide statistics

Reuses `storage.get_user_recommendation_data()` - the exact same
ownership-filtered query `/api/recommendations` already uses - rather than
a second, parallel data-fetching path. `analytics.py` (pure functions, no
DB/network access, just like `recommendations.py`) turns that into:

| Field | Definition |
|---|---|
| `completion_rate` | `completed_interviews / total_interviews` (every interview the account has, completed or not). `null` when `total_interviews` is 0 - never shown as 0%, which would look like a failing grade rather than "no data." |
| `average_score` | Mean of `total_score` across every **evaluated answer**, not an average of per-interview averages - an interview with more evaluated questions contributes proportionally more. This is the same definition `/api/interviews`' per-item `average_score` uses, just computed across the whole account instead of one interview. |
| `highest_score` / `most_recent_score` | Both drawn only from evaluated answers; "most recent" is by the answer's own evaluation timestamp, not the interview's creation date. |
| `by_category` | Only categories with at least one evaluated answer appear at all - a category you've never attempted is never listed, let alone implied to be weak. |
| `by_dimension` | Always present (when `evaluated_answers > 0`) for all four rubric dimensions, since every evaluated answer has a value for each one. |
| `strongest_dimension` / `weakest_dimension` | `null` unless there are at least 3 evaluated answers (`recommendations.MIN_SAMPLES_FOR_TREND`, reused rather than a second magic number) - avoids calling something "your strongest area" from a single lucky answer. |
| `progress` | One `{evaluated_at, score}` point per evaluated answer, in chronological order - this is what the frontend charts. |
| `progress_sufficient` | `true` only when there are 2+ points - a single data point cannot show a trend, so the frontend shows an explanation instead of a one-dot "chart" when this is `false`. |

Missing evaluations are never treated as a score of `0` anywhere in this
module - an account with interviews but no evaluations gets `evaluated_answers: 0`
and every score field `null`, not a wall of zeroes that would look like
poor performance.

## How the frontend uses this API

`prepai/js/api.js` (`window.PREP_API`) is the only place the backend URL is
hardcoded. If the backend is unreachable or rejects a request, the frontend
does **not** silently pretend a local/offline attempt came from the server:
it shows a clear message and, on the setup screen, offers a distinct
"Continue in Offline Demo Mode" button the user must click on purpose. A
completed attempt's stored `source` field (`backend` or `offline`) records
honestly which one actually happened, and the results page's wording
reflects it.

A question you already submitted to the backend can't be re-submitted if
you go back and edit it - the API itself rejects that with `409` (now
enforced by the database itself, not just application code - see below),
and the frontend respects that by locking that question's answer box
instead of trying to force an update.

On `results.html`, a completed attempt that was actually submitted to the
backend (`source: 'backend'`) shows an **"Evaluate with AI"** button under
each answered question. This is an explicit, per-question, user-initiated
action - the page never evaluates anything automatically on load or on
completion, so viewing your results can never by itself trigger a paid AI
call. If the feature is disabled (the default) or the request fails, the
button re-enables with a clear message instead of showing a fake score.
Older attempts saved before Phase 8, or ones made entirely offline, simply
don't show the button at all (there's no backend session to evaluate
against).

On `analytics.html`, a new "Personalized Recommendations" section loads
automatically (unlike the evaluate button, this makes no AI call and costs
nothing, so there's no reason to gate it behind a click). If you're not
logged in, it shows a plain sign-in prompt instead of an error. If the
request fails, it shows a message and a "Try again" button rather than a
blank or broken section.

On `history.html` (Phase 10), a new **"Your Account History"** section
calls `GET /api/interviews` and loads automatically for the same reason -
no AI call, no cost. The **existing table below it is completely
unchanged** and still reads only `P.attempts`/`localStorage`; it has just
been relabeled "Local Browser History (This Device Only)" so the two are
never confused. Each account-history row links to
`results.html?session=<real backend session_id>` - a **new** way to open
`results.html` that fetches live from the backend (via the now-extended
`GET /api/interviews/{session_id}`), completely independent of
`localStorage`. The original `results.html?id=<localStorage demo id>` path
is untouched. This is what makes account history actually useful across
devices: a `localStorage` id from one browser means nothing on another
device, but a `?session=` link works anywhere you're logged into the same
account.

On `analytics.html` (Phase 10), a new **"Your Account Analytics"** section
calls `GET /api/analytics` and renders real metrics, a category/dimension
breakdown, and (only when there are 2+ evaluated answers) a progress chart
reusing the existing `createChart()` from `chart.js` - no new charting code
or library was added. The pre-existing sample-data metrics/chart/two-col
sections above it are completely unchanged.

## What's NOT implemented yet (future phases)

- **No "re-evaluate" button.** The first successful evaluation of a
  question is permanent - see "Idempotency" above.
- **No social login, email verification, or password reset.** Accounts are
  email+password only (see "Authentication and accounts" below).
- No way to **resume an in-progress** interview after a page refresh - if
  you reload `practice.html` mid-interview, that session's live UI state is
  lost (though its data is safe on the server). As of Phase 10, you *can*
  look up a session afterward - via "Your Account History" on
  `history.html`, logged in - to see whatever was answered and evaluate
  it; you just can't resume typing where you left off.
- No retry logic for AI requests - a single failed attempt returns an error
  immediately rather than silently retrying (and re-billing).
- **No dismissed/tracked recommendations.** There's no way to mark a
  recommendation as seen or acted on - the same evidence always produces
  the same recommendation again on the next page load. Deliberately left
  as documented future work rather than added speculatively this phase.
- **No optional AI-generated wording for recommendations.** See
  "Personalized recommendations" above for why this was skipped.
- **No per-interview detail page for the legacy localStorage demo
  attempts' backend data.** They never had one - Phase 10 adds server
  history for *new* attempts going forward, it doesn't retroactively
  attach old local-only attempts to the server.
- **No search or filtering on account history yet** - just newest-first
  pagination. The legacy local table above it keeps its own existing
  date-range/type filters, unchanged.

## Database (Phase 6)

Interview sessions, their questions, and submitted answers are stored in a
real SQLite database file and **survive a backend restart.** Before Phase 6,
this was a plain Python dictionary that was wiped on every restart - that
limitation is gone now.

**Location:** `backend/data/prepai.db` by default (created automatically on
first use - the folder doesn't need to exist beforehand). Override with the
`DATABASE_PATH` environment variable in your `.env` if you want the file
somewhere else. The file (and any SQLite journal/WAL files) is excluded by
`.gitignore` - it is never committed, since it can contain real interview
answers.

**Tables:**

| Table | Stores | Key points |
|---|---|---|
| `interviews` | One row per session: `id`, `role`, `category`, `difficulty`, `question_count`, `status`, `question_source`, `created_at`, `completed_at`, and `user_id` (see Phase 7 below - `NULL` for anonymous/offline interviews, a real account's `id` otherwise). | `id` is the same session ID the frontend already uses. `user_id` has an index but, deliberately, no foreign-key constraint - see "Why no FK on `user_id`" below. |
| `questions` | One row per question: which `interview_id` it belongs to, its `id` (`q1`, `q2`, ...), its `text`, and its `position` (display order). | Primary key is `(interview_id, id)` - question IDs like `q1` are only unique *within* one interview, not globally. |
| `answers` | One row per submitted answer: `interview_id`, `question_id`, `answer_text`, `submitted_at`. | A `UNIQUE (interview_id, question_id)` constraint enforces "no duplicate answer" at the database level, not just in application code. A foreign key ties every answer to a question that must actually exist in that same interview. |
| `evaluations` (Phase 8) | One row per evaluated question: `interview_id`, `question_id`, `total_score` plus the four dimension scores, `relevance_assessment`/`correctness_assessment`/`explanation` text, `strengths`/`weaknesses`/`suggestions` (each stored as a JSON-encoded list of strings), an optional `example_answer`, which `model` produced it, and `created_at`. | Same `UNIQUE (interview_id, question_id)` + foreign-key pattern as `answers` - this is what makes evaluation idempotent per question and guarantees an evaluation can never attach to a question outside its own interview. |

**How it connects to FastAPI:** `db.py` opens a plain `sqlite3` connection
(Python's built-in module - no ORM) whenever `storage.py` needs one, turns
on foreign-key enforcement (SQLite has it off by default), and makes sure
the four tables above exist (`CREATE TABLE IF NOT EXISTS`, which never
drops or recreates a table that's already there - the `evaluations` table
was added this way on top of an existing Phase 6/7 database, with zero risk
to the `interviews`/`questions`/`answers`/`users`/`sessions` rows already in
it). `storage.py` keeps the
exact same function names it had in Phase 5 (`create_session`,
`get_session`, `record_answer`, `complete_session`), so `main.py`'s route
handlers did not need to change - they still don't know or care that the
storage underneath is now a real database instead of a dictionary.

Each interview's creation (the interview row plus all its question rows) is
written as a single database transaction - if anything in that batch fails,
none of it is saved, so you never end up with a half-created interview.

**How sessions survive a restart:** `storage.py` never keeps a connection
or any session data in memory between requests - every function opens a
fresh connection, does its one piece of work, and closes it again. That
means there is nothing in RAM to lose when the process stops; the next
request (even from a brand-new process) just reads the same file from disk.
This was verified by actually stopping and restarting the real backend
process during this phase - see the final report.

**Backing up your development database:** it's a single file, so just copy
it while the backend isn't running: `copy backend\data\prepai.db backend\data\prepai.db.bak`.

**Current limitations:** no database migrations tooling (schema changes so
far have only ever added tables/columns, never changed existing ones), no
connection pooling (fine at this scale).

### Why no foreign key on `interviews.user_id`

SQLite can't add a foreign-key constraint to a column on an *existing*
table without rebuilding the whole table (copy all rows into a new table,
drop the old one, rename) - and that rebuild is exactly the kind of risky,
hard-to-verify operation this project avoids doing to a database that might
already hold real data. Instead, `user_id` has a plain index (fast lookups)
and ownership is enforced entirely in application code (`main.py`), which is
where the real security boundary has to live anyway - a database-level FK
would not stop someone from trying to access another user's interview by
guessing its ID; only the ownership check in the route handler does that
(see "Authentication and accounts" below).

## Authentication and accounts (Phase 7)

Accounts are **optional**. Everything that worked before Phase 7 - the
offline demo, anonymous interviews, Settings' backend-health indicator,
AI/fixed question generation - still works exactly the same with no
account at all. Logging in only adds one thing: interviews you create while
logged in are tied to your account, and only you can read, answer, or
complete them afterward.

### New tables

| Table | Stores |
|---|---|
| `users` | `id`, a normalized-lowercase, unique `email`, an Argon2id `password_hash` (never the plain password), `created_at`. |
| `sessions` | A random opaque `token` (the thing the cookie actually carries), a matching random `csrf_token`, which `user_id` it belongs to, and `created_at`/`expires_at`. |

Both are created with `CREATE TABLE IF NOT EXISTS`, so running this on an
existing Phase 6 database is safe - your existing `interviews`/`questions`/
`answers` rows are completely untouched, and every interview that already
existed keeps `user_id = NULL` (unowned) forever; nothing automatically
claims old interviews for a new account, and there is no "transfer
ownership" feature at all.

### Password hashing

Passwords are hashed with **Argon2id** (`argon2-cffi`, the library OWASP
currently recommends) before anything touches the database. The plain
password is never stored, logged, or included in any response or error
message. Login compares against the stored hash in roughly constant time
even for an unknown email, specifically so a timing difference can't be
used to guess which emails have accounts.

### How sessions work (and why there's no app-wide secret key)

A session is **not** a JWT. Logging in or registering generates a random,
unguessable token (`secrets.token_urlsafe(32)`) and stores it in the
`sessions` table; that token is the only thing the cookie carries. Every
request, the backend looks the token up in the database - if it's there and
not expired, you're logged in as whoever it belongs to; if not, you aren't.
This means:
- There is no secret key to configure or leak - revoking a session is just
  deleting its database row, which logout does immediately.
- A session is always a **brand-new** random value issued by the server -
  nothing a client sends is ever accepted as a session identifier on
  login/register, which is what prevents session fixation.
- Sessions expire after `SESSION_LIFETIME_DAYS` (default **7 days** - see
  `.env.example`); an expired token is treated exactly like no token at all.

### Cookies and CORS

Two cookies get set on successful login/register:

| Cookie | HttpOnly | Purpose |
|---|---|---|
| `prepai_session` | Yes | The session token. JavaScript can never read this - only the browser sends it back automatically. |
| `prepai_csrf` | No | A matching random value the frontend reads via `document.cookie` and echoes back as an `X-CSRF-Token` header on state-changing requests. |

Both use `SameSite=Lax`. Because the frontend (`127.0.0.1:5500`) and backend
(`127.0.0.1:8000`) are the same *site* (same host, `127.0.0.1`) even though
they're different *origins* (different port), `SameSite=Lax` cookies are
still sent on these cross-port `fetch()` calls - the stricter `SameSite=None`
(which would additionally require `Secure`, i.e. HTTPS) isn't needed for
this specific setup. `main.py`'s CORS config explicitly lists the one
allowed origin and sets `allow_credentials=True` - **never** a wildcard
origin, which browsers refuse to combine with credentials anyway.

**For local HTTP development**, cookies are issued without the `Secure`
attribute (`SESSION_COOKIE_SECURE` defaults to `false`), which is required
since this project runs over plain `http://127.0.0.1`. **If you ever deploy
this over real HTTPS**, set `SESSION_COOKIE_SECURE=true` in that
environment's `.env` - leaving it `false` in production would let the
cookie be sent over an unencrypted connection.

### CSRF protection

Every state-changing request made *while logged in* (`POST /api/interviews`,
`.../answers`, `.../complete`, `POST /api/auth/logout`) must include the
`X-CSRF-Token` header matching the `prepai_csrf` cookie, or the backend
rejects it with `403`. `prepai/js/api.js` does this automatically for every
request. Anonymous requests (no session cookie at all - the existing
offline/demo flow) are never asked for this header, since there is no
cookie-based ambient authority for a forged request to exploit in the first
place.

### Ownership enforcement

`POST /api/interviews` tags a new interview with your account's `user_id`
if you're logged in, or leaves it `NULL` (anonymous) if you're not - this
happens automatically based on whether a valid session cookie is present;
there is no separate toggle. For `GET /api/interviews/{id}`, `.../answers`,
and `.../complete`:
- An **unowned** (`user_id IS NULL`) interview keeps the exact Phase 4-6
  behavior - open to anyone who has the session ID, logged in or not.
- An **owned** interview is only visible/usable by the account that created
  it. Anyone else - a different logged-in account, or no account at all -
  gets the same `404 Interview session not found` a nonexistent ID would
  give, so the response never confirms that someone else's private
  interview even exists.

This check happens in `main.py` on every request; a client can never
influence whose interview it is by sending its own `user_id` - that value
is only ever read from the server-validated session.

### Using it from the frontend

Settings page → **Account** section: email + password fields with
**Create Account** / **Log In** buttons when logged out, or your email and
a **Log Out** button when logged in. Error messages (wrong password,
duplicate email, unreachable server) show inline. No other page changed -
`practice.html`'s interview flow works identically whether or not you're
logged in, because `prepai/js/api.js` now sends `credentials: 'include'`
(and the CSRF header, when applicable) on every call without any page
needing to know about it.

### Known limitations / not a production security audit

- No password reset or email verification flow.
- No rate limiting on login attempts (a determined attacker could still
  brute-force a weak password over many requests).
- No "log out everywhere" - logout only deletes the one session the request
  came from.
- No automatic cleanup of expired session rows (they're just ignored, not
  deleted) - harmless at prototype scale, but would grow unbounded forever.
- This has not been through a real security review or threat-modeling
  exercise and should not be described as "production-secure" without one.

## Project files

| File | Purpose |
|---|---|
| `main.py` | FastAPI app and route handlers: auth routes, interview routes (now ownership- and CSRF-aware), CORS config, loads `.env` at startup. |
| `auth.py` | Password hashing, user accounts, and session/CSRF token management (Phase 7) - isolated from both `storage.py` and the route handlers. |
| `db.py` | SQLite connection + schema setup (Phase 6/7: `interviews`, `questions`, `answers`, `users`, `sessions`), separate from the route handlers and repository logic. |
| `storage.py` | The session/question/answer repository. Same public functions as Phase 5 (`create_session`, `get_session`, `record_answer`, `complete_session`), now backed by the database instead of a dictionary, and now also tracking each interview's `user_id`. |
| `ai_provider.py` | The AI question-generation service (OpenAI), isolated from the route handlers. Validates input, makes one request with a timeout, validates the output, never logs the API key. |
| `evaluation_provider.py` | The AI answer-evaluation service (Phase 8) - separate file, separate flag, separate exception types from `ai_provider.py`. Computes the 0-100 total itself rather than trusting the model's arithmetic; never logs the API key or the candidate's answer. |
| `recommendations.py` | The deterministic recommendation engine (Phase 9) - pure functions, no DB access and no AI calls at all; takes already-fetched, already-owned data in and returns a ranked recommendation list out. |
| `analytics.py` | Pure analytics calculations (Phase 10) - same no-DB, no-network pattern as `recommendations.py`, and reuses its constants rather than duplicating them. |
| `schemas.py` | Pydantic models that validate requests and shape responses, including `question_source`, `RegisterRequest`/`LoginRequest`/`UserOut`, `EvaluationOut`, `RecommendationOut`/`RecommendationsOut`, `InterviewSummaryOut`/`InterviewListOut`, `AnalyticsOut`. |
| `questions.py` | Small sample question bank (Technical/HR/Behavioral), mirroring `prepai/js/data.js`. Used whenever AI generation is off or unavailable. |
| `tests/test_api.py` | Automated pytest tests covering the interview API, including AI-enabled/disabled/failure cases and a database-error case (all mocked). |
| `tests/test_ai_provider.py` | Unit tests for `ai_provider.py` using a fake HTTP client - no real network calls, no API key, no cost. |
| `tests/test_evaluation_provider.py` | Unit tests for `evaluation_provider.py`: valid scoring, out-of-range/malformed responses, blank answers, provider failures, category-specific prompt content - fake HTTP client only. |
| `tests/test_evaluation_api.py` | API-level evaluation tests: persistence, idempotency, failed-evaluation-saves-nothing, ownership isolation, CSRF, anonymous access. |
| `tests/test_recommendations.py` | Pure logic tests for `recommendations.py`: weak/strong/inconsistent detection, missing-data handling, ordering determinism, recommendation count limit - no DB, no network. |
| `tests/test_recommendations_api.py` | API-level tests: authentication required, cross-account privacy, anonymous interviews never attributed, database-error handling. |
| `tests/test_history_api.py` | `GET /api/interviews` (list + pagination + ownership + counts) and the extended `GET /api/interviews/{id}` (per-question evaluations, privacy). |
| `tests/test_analytics.py` | Pure logic tests for `analytics.py`: correct aggregates, missing-data-not-zero, determinism, minimum-sample gating - no DB, no network. |
| `tests/test_analytics_api.py` | API-level tests: authentication required, cross-account isolation, anonymous exclusion. |
| `tests/test_storage.py` | Tests for the SQLite persistence layer directly: schema, ordering, duplicate rejection, foreign keys, transaction rollback, and restart simulation. |
| `tests/test_auth.py` | Registration, login, logout, session expiry, CSRF enforcement, and cross-account ownership isolation tests. |
| `tests/conftest.py` | Points every test at its own temporary database file, so running the test suite never touches `backend/data/prepai.db`. |
| `requirements.txt` | fastapi, uvicorn, pytest, httpx, python-dotenv, argon2-cffi. (SQLite itself is part of Python's standard library.) |
| `.env.example` | Placeholder config, safe to commit. Copy to `.env` (never committed) to actually configure anything. |

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

This never makes a real network call and never needs an API key - every AI
provider test (question generation in `tests/test_ai_provider.py`,
evaluation in `tests/test_evaluation_provider.py`) injects a fake HTTP
client, and the API-level tests (`tests/test_api.py`,
`tests/test_evaluation_api.py`) monkeypatch `ai_provider`/
`evaluation_provider` functions directly - so nothing can incur a charge
just by running tests, even if you happen to have a real `.env` configured
with live keys on the same machine. `tests/test_recommendations.py` needs
none of this at all - `recommendations.py` makes no network or database
calls, so those tests just call its functions directly with plain
in-memory data.

It also never touches your real development database - `tests/conftest.py`
points every test at its own fresh temporary database file instead, so
`tests/test_auth.py`'s registered test accounts never end up in
`backend/data/prepai.db`.

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

### Example: registering, logging in, and creating an owned interview

curl doesn't manage cookies between calls by itself, so pass `-c jar.txt`
to save them and `-b jar.txt` to send them back on the next call:

```powershell
# 1. Register (this also logs you in and sets the cookies)
curl.exe -c jar.txt -X POST http://127.0.0.1:8000/api/auth/register `
  -H "Content-Type: application/json" `
  -d '{"email":"you@example.com","password":"a-long-enough-password"}'

# 2. Read the CSRF cookie's value out of jar.txt (it's the prepai_csrf line's last column),
#    then use it as a header on any state-changing call:
curl.exe -b jar.txt -X POST http://127.0.0.1:8000/api/interviews `
  -H "Content-Type: application/json" -H "X-CSRF-Token: PASTE_IT_HERE" `
  -d '{"role":"Backend Developer","category":"hr","difficulty":"easy","question_count":2}'
# -> this interview's user_id is now set - only you can read/answer/complete it

# 3. Check who you are
curl.exe -b jar.txt http://127.0.0.1:8000/api/auth/me

# 4. See your recommendations (free - no AI call, works with zero evaluations)
curl.exe -b jar.txt http://127.0.0.1:8000/api/recommendations

# 5. See your interview history (paginated, newest first)
curl.exe -b jar.txt "http://127.0.0.1:8000/api/interviews?limit=10&offset=0"

# 6. See your account-wide analytics
curl.exe -b jar.txt http://127.0.0.1:8000/api/analytics
```

### Example: evaluating an answer (only after you set AI_EVALUATION_ENABLED=true and a real key - see "AI answer evaluation" above; this makes a real, paid request)

```powershell
# Using SESSION_ID and a question_id from an interview you already answered:
curl.exe -X POST http://127.0.0.1:8000/api/interviews/SESSION_ID/questions/q1/evaluate `
  -b jar.txt -H "X-CSRF-Token: PASTE_IT_HERE"
# (omit -b/-H entirely if the interview was created anonymously, with no login)
```

Example response shape:

```json
{
  "session_id": "...", "question_id": "q1",
  "total_score": 78, "relevance_score": 24, "correctness_score": 29,
  "completeness_score": 18, "clarity_score": 7,
  "relevance_assessment": "Directly answers what was asked.",
  "correctness_assessment": "Technically accurate with one minor gap.",
  "explanation": "A strong answer that could be more complete.",
  "strengths": ["Clear structure", "Correct use of terminology"],
  "weaknesses": ["Did not mention time complexity"],
  "suggestions": ["Add Big-O analysis of the approach"],
  "example_answer": null,
  "model": "gpt-4o-mini", "created_at": "2026-...",
  "note": "AI-generated estimate for practice purposes - not an objective or official assessment."
}
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
| AI generation is enabled but fails (timeout, auth, rate limit, outage, or an unusable response) | 503 |
| Invalid email format on registration | 422 |
| Password shorter than 8 characters on registration | 422 |
| Registering an email that's already taken | 409 |
| Login with an unknown email, or the wrong password (same status/style for both, on purpose) | 401 |
| `GET /api/auth/me` with no valid session | 401 |
| A state-changing request made while logged in, without a matching `X-CSRF-Token` header | 403 |
| Reading/answering/completing an interview owned by a different account (or by no one, while you're someone else) | 404 |
| Evaluating a question that exists but has no submitted answer yet | 409 |
| Evaluating an unknown session or question | 404 |
| Evaluating an interview you don't own (or no one owns, while you're someone else) | 404 |
| Evaluation requested but `AI_EVALUATION_ENABLED` is off, misconfigured, or the provider call fails for any reason | 503 |
| Re-evaluating an already-evaluated question | 200 - returns the existing stored result, not an error |
| `GET /api/recommendations` with no valid session (recommendations have no anonymous equivalent) | 401 |
| `GET /api/recommendations` for an account with no completed interviews, or interviews but no evaluations | 200 - a generic, clearly-labeled recommendation, not an error |
| `GET /api/interviews` or `GET /api/analytics` with no valid session (no anonymous equivalent) | 401 |
| `GET /api/interviews` or `GET /api/analytics` for an account with no interviews/evaluations | 200 - an honest empty/null response, never an error or a fabricated zero |
| An answer longer than 10,000 characters (Phase 11) | 422 |

## Security audit and stabilization (Phase 11)

This phase audited the existing implementation (Phases 4-10) against a
security/correctness checklist rather than adding features. It re-read every
backend module and the frontend files that call the API, ran the full test
suite, and exercised live cross-account, CSRF, and CORS scenarios against a
running server before concluding anything was safe.

### What was checked and confirmed correct (by reading the code and running live tests, not by assuming prior reports)

- **Authentication**: Argon2id hashing, a timing-equalized check for an
  unknown email (hashes against a decoy to avoid leaking which emails are
  registered), identical `401` wording for "unknown email" and "wrong
  password", brand-new random session tokens on every login/register (no
  session fixation), expired/garbage tokens treated as "not logged in" with
  no error.
- **Session/CSRF cookies**: `prepai_session` is `HttpOnly`; `prepai_csrf` is
  readable by JavaScript (by design - the double-submit pattern needs that);
  both are `SameSite=Lax`. Verified live: creating/answering/completing an
  interview or logging out while authenticated and *not* sending
  `X-CSRF-Token` (or sending a wrong one) is rejected with `403` in every
  case; anonymous (no session cookie) requests are never asked for it.
- **CORS**: live `curl` requests with an `Origin: http://evil.example.com`
  header never got an `Access-Control-Allow-Origin` back (only the one
  configured origin does), so a browser would refuse to let a script on any
  other site read the response even with credentials involved.
- **Ownership/cross-account isolation**: registered two real accounts
  against a running server and confirmed one account's `GET`/answer/
  complete/evaluate requests against the other's interview all return the
  exact same `404 Interview session not found` a nonexistent session ID
  would - never a `403` or any other hint that the interview exists.
  `GET /api/interviews`, `GET /api/analytics`, and `GET /api/recommendations`
  were confirmed to return only the caller's own data (empty/zeroed for a
  fresh account, never another account's rows). Anonymous (unowned)
  interviews were confirmed to stay visible to everyone, as designed, and
  never appear in any account's `/api/interviews` list.
- **AI cost safety**: with no `.env` file present at all during this audit
  (confirmed on disk), both `AI_QUESTIONS_ENABLED` and `AI_EVALUATION_ENABLED`
  default to off, every interview correctly used `question_source: "fixed"`,
  and every evaluate request correctly returned `503 AI answer evaluation is
  not configured on this server.` - no real OpenAI request was ever made
  during this phase. `evaluation_provider.py` was re-confirmed to compute
  `total_score` itself from the four validated dimension scores, never from
  a model-reported total.
- **Idempotency**: submitting the same answer twice returns `409` (not a
  silent overwrite); the database's `UNIQUE (interview_id, question_id)`
  constraints back both the answers and evaluations idempotency guarantees,
  not just the application-level checks in front of them.
- **Persistence**: stopped and restarted the real backend process during
  this phase and confirmed a previously created interview and its submitted
  answer were both still present afterward, unchanged.
- **Secrets/config hygiene**: no `.env` file exists on disk in this
  environment; `backend/.env` is confirmed untracked by git; `.env.example`
  contains only commented-out placeholders; `backend/data/` (the real
  database), `.venv/`, `__pycache__/`, and `*.pyc` are all excluded by
  `.gitignore`; a repository-wide search found no hardcoded API keys or
  secret-like strings in any tracked `.py`/`.js` file. The backend has no
  logging calls at all (`grep` for `print(`/`logging.` in the source found
  nothing), so there is no log file that could ever contain a password,
  session token, or submitted answer text.
- **Dependencies**: all six entries in `requirements.txt`
  (`fastapi`, `uvicorn[standard]`, `pytest`, `httpx`, `python-dotenv`,
  `argon2-cffi`) are actually imported and used somewhere in the backend;
  none are unused, duplicated, or an unexplained major-version pin.

### One verified defect found and fixed

**Unbounded answer length.** `AnswerRequest.answer` had no `max_length`, so
a client could submit an arbitrarily large string (megabytes or more) that
would be persisted to the database with no limit - an abuse/resource-exhaustion
gap, not something any existing test covered. Fixed with a single
`Field(..., max_length=10000)` in `schemas.py` (10,000 characters is
generous for a spoken-interview-style answer while still bounding the worst
case), plus a new regression test
(`tests/test_api.py::test_submit_oversized_answer_rejected`) confirming a
10,001-character answer is rejected with `422` and a 10,000-character one is
still accepted. Verified live against a freshly started server, not just in
the test suite.

### Testing the main workflow and account isolation yourself

```powershell
# Terminal 1: backend
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.venv\Scripts\Activate.ps1
uvicorn main:app --reload

# Terminal 2: two separate cookie jars simulate two different accounts
curl.exe -c a.jar -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d '{"email":"a@example.com","password":"PasswordAAA1"}'
curl.exe -c b.jar -X POST http://127.0.0.1:8000/api/auth/register -H "Content-Type: application/json" -d '{"email":"b@example.com","password":"PasswordBBB1"}'
# Read the prepai_csrf value out of a.jar, then create an interview as account A:
curl.exe -b a.jar -X POST http://127.0.0.1:8000/api/interviews -H "Content-Type: application/json" -H "X-CSRF-Token: PASTE_A_CSRF_HERE" -d '{"role":"X","category":"technical","difficulty":"easy","question_count":1}'
# Using account A's session_id but account B's cookie jar - should return 404, not the interview:
curl.exe -b b.jar http://127.0.0.1:8000/api/interviews/SESSION_ID_FROM_A
```

### Pre-deployment checklist (not fixed this phase - documented gaps, not oversights)

None of the items below are code defects; they are standing limitations that
should be addressed before any real/public deployment, separate from the
local-prototype setup this project currently targets:

- **No rate limiting** on login, registration, or any other endpoint - a
  determined attacker could brute-force a weak password, or spam account
  creation, over many requests. Nothing in this codebase throttles that.
- **`SESSION_COOKIE_SECURE` defaults to `false`**, which is *correct* for
  local `http://127.0.0.1` development but **must** be set to `true` in any
  environment actually served over HTTPS - otherwise the session cookie
  could be sent in the clear.
- **CORS is hardcoded to one local origin** (`http://127.0.0.1:5500`) in
  `main.py`. A real deployment must change `allow_origins` to the real
  frontend domain(s) - never to a wildcard, which browsers refuse to combine
  with credentials anyway.
- **`uvicorn --reload`** (used in this README's dev instructions) must never
  be used in production - it is a development convenience that watches
  files for changes and is not meant for production serving. A production
  deployment should run multiple workers behind a process manager instead.
- **SQLite + multiple workers is a real constraint**: SQLite handles
  concurrent reads fine but serializes writes, and this project opens a
  fresh connection per request with no pooling. This is adequate at
  prototype/single-user scale but would need a different database (e.g.
  PostgreSQL) or a single-writer architecture before handling meaningful
  concurrent write traffic.
- **No email verification or password reset** - accounts are email+password
  only, as already noted above. There is also no "log out everywhere" and no
  cleanup job for expired session rows (harmless at this scale, but would
  grow unbounded in a long-lived deployment).
- **No structured application logging or monitoring** - there is currently
  nothing to alert on repeated failed logins, AI provider errors, or
  unexpected 500s in a real deployment; `main.py`'s global exception handler
  returns a safe generic message to the client but does not currently record
  the real error anywhere for an operator to see.
- Passing automated tests (164 pre-existing + 1 new = 165, all passing - see
  below) demonstrates the tested behaviors work as intended; it is **not**
  itself evidence of production-readiness, security review, or performance
  under real load, none of which happened this phase.
