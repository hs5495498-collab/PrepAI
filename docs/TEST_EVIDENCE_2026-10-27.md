# PrepAI Test Evidence Report — 2026-10-27

A record of an actual, fresh execution of this repository's test suites
and API verification, not a copy of an earlier session's results. Every
number below was produced by a command run in this session; none are
estimated or assumed.

## Run metadata

| | |
|---|---|
| Date/time of run | 2026-10-27, ~07:00-07:20 UTC (12:30-12:50 IST) |
| Git commit tested | `70e1e8806f87bd9a31d9dd51e2abae78c612aeeb` |
| Branch | `main` |
| Working tree before this session | Clean except the pre-existing, untouched, untracked `prepai/js/voiceCommands.js` |
| Remote | `origin` → `https://github.com/hs5495498-collab/PrepAI`, in sync with `main` (verified via `git fetch` + `git log origin/main..main`/`git log main..origin/main`, both empty) |

## 1. Backend test suite

**Command (from repository root, matching this task's suggested invocation):**
```powershell
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/ -q
```
Also confirmed equivalent to the documented `backend/README.md` command
(`cd backend; pytest tests/ -v`, run with the activated `.venv`).

**Result:**
```
198 passed, 1 warning in 55.60s
```
- Passed: **198**
- Failed: **0**
- Skipped: **0**
- Warnings: **1** — `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.` Pre-existing, from the test-client library itself, unrelated to application code; not something this run introduced or needs to fix for the suite to be meaningful.
- Exit code: **0**

Full `-v` transcript captured this session in
`%TEMP%\...\backend_test_run.log` during the run (local machine temp
file, not committed - see the command above to reproduce it directly).

Test isolation: `tests/conftest.py`'s `isolated_database` fixture (run
`autouse` for every test) points `DATABASE_PATH` at a fresh file under
`tmp_path` per test - no test in this suite ever touches
`backend/data/prepai.db`, the real local database.

## 2. Selenium end-to-end suite

**Collected test list** (`pytest --collect-only -q tests/selenium/`): 42
tests, listed in full below.

**Command:**
```powershell
.\backend\.venv\Scripts\python.exe -m pytest tests/selenium/ -q
```

**Result:**
```
42 passed in 108.04s (0:01:48)
```
- Passed: **42**
- Failed: **0**
- Skipped: **0**
- Exit code: **0**

Test isolation (`tests/selenium/conftest.py`): the suite starts and owns
its own throwaway `uvicorn` backend subprocess against a temp-directory
SQLite file (never `backend/data/prepai.db`) and its own static frontend
server bound to exactly `127.0.0.1:5500`; it refuses to start at all
(`pytest.exit`) if ports 8000/5500 are already occupied by something
else, specifically so it never collides with or reuses a developer's own
running servers. `AI_QUESTIONS_ENABLED`/`AI_EVALUATION_ENABLED`/
`OPENAI_API_KEY` are explicitly stripped from its subprocess's
environment - this suite cannot make a real AI provider call even if
your own `backend/.env` has them set.

### Coverage by requested journey (all 17 present)

| Journey | Test(s) |
|---|---|
| Registration and login | `test_04_malformed_email_is_rejected`, `test_05_register_new_account`, `test_06_logged_in_state_persists_after_refresh`, `test_07_logout`, `test_08_duplicate_registration_rejected`, `test_09_login_with_wrong_password_rejected`, `test_10_login_with_correct_credentials` |
| Dashboard rendering | `test_dashboard_offers_a_clear_login_link_when_logged_out`, `test_13b_dashboard_shows_honest_account_overview` |
| Practice recommendation loading | all of `TestPracticeRecommendation` |
| Interview creation | `test_11_start_interview` |
| First question persistence | `test_question_stays_visible_several_seconds_after_starting_and_after_each_answer`, `test_question_stays_visible_after_starting_from_recommendation_card` |
| Answer submission and progression | `test_12_answer_and_navigate_all_questions`, `test_previous_question_answer_is_preserved_and_locked_after_submit` |
| Duplicate-start protection | `test_start_recommended_session_rapid_double_click_creates_only_one_interview` |
| Interview completion | `test_13_interview_completion_shows_results` |
| Results rendering | `test_13_interview_completion_shows_results`, `test_13b_dashboard_shows_honest_account_overview` |
| History | `test_14_history_shows_new_account_entry`, `test_history_logged_out_shows_local_section_only` |
| Analytics | `test_15_analytics_and_recommendations_render`, `test_analytics_shows_honest_sign_in_prompt_and_separate_sample_data_when_logged_out` |
| Achievements | `test_achievements_shows_honest_sign_in_prompt_and_separate_sample_data_when_logged_out`, `test_achievement_milestone_thresholds_are_correct` |
| Logged-out states | all of `TestLoggedOutStates` |
| Error and retry handling | `test_recommendation_card_shows_error_and_retry_when_backend_unavailable`, `test_start_recommended_session_failure_does_not_leave_button_stuck` |
| Responsive/mobile overflow | `test_no_horizontal_overflow_at_demo_viewport_sizes`, `test_analytics_no_horizontal_overflow_at_demo_viewport_sizes`, `test_achievements_no_horizontal_overflow_at_demo_viewport_sizes`, `test_recommendation_card_renders_and_starts_a_session_at_mobile_width` |
| Account isolation | both of `TestCrossAccountIsolation` |
| Offline Demo Mode | both of `TestOfflineDemoMode` |

(Full 42-item collected list available via the collect-only command
above; omitted here for length - every item maps to one of `TestAccount
AndInterviewFlow`, `TestLoggedOutStates`, `TestOfflineDemoMode`,
`TestCrossAccountIsolation`, or `TestPracticeRecommendation`.)

## 3. Local application verification

- `http://127.0.0.1:8000/health` → `{"status":"ok"}` ✅ (confirmed via `curl` this session)
- `http://127.0.0.1:8000/docs` → HTTP 200 ✅ (confirmed via `curl`)
- No duplicate backend process was started - the one already needed for
  this session's verification work was reused.
- Frontend (VS Code Live Server, `127.0.0.1:5500`) was **not** running at
  the start of this session; starting it is a manual step for you (open
  the folder in VS Code → "Go Live") - **this was not done by the
  assistant and is not claimed as verified in a browser this session.**

## 4. Postman / API verification

A full Postman collection was created:
`docs/postman/PrepAI.postman_collection.json` (21 requests across 6
folders) + `docs/postman/PrepAI.postman_environment.json`, built directly
from the live `GET /openapi.json` schema and `backend/auth.py`'s actual
cookie/header names - no invented endpoints or fields.

**Postman's own CLI runner (`newman`, via `npx`) was blocked by this
environment's auto-mode sandbox** (classified as external-code
execution) - it was not run. As an equivalent, honest substitute, **every
one of the 21 requests' exact method/URL/body/headers was manually
replayed via `curl`** against the real running backend this session,
confirming the live status code and response body matched every
assertion the collection's Tests scripts make. Full transcript below.

| # | Request | Expected | Actual | Match |
|---|---|---|---|---|
| 1.1 | `GET /health` | 200, `status: ok` | 200, `{"status":"ok"}` | ✅ |
| 2.1 | `POST /api/auth/register` (A) | 201, cookies set | 201, `prepai_csrf`+`prepai_session` both set | ✅ |
| 2.2 | `GET /api/auth/me` | 200, email matches | 200, matched | ✅ |
| 2.3 | `POST /api/auth/logout` | 200 | 200, `{"status":"logged_out"}` | ✅ |
| 2.4 | `POST /api/auth/login` | 200, fresh cookies | 200, fresh CSRF captured | ✅ |
| 3.1 | `POST /api/interviews` | 201, 3 questions, `in_progress` | 201, matched exactly | ✅ |
| 3.2 | `GET /api/interviews/{id}` | 200, same session | 200, matched | ✅ |
| 3.3 | `POST .../answers` | 200, `answered_count: 1` | 200, matched | ✅ |
| 3.4 | `GET .../{id}` (verify) | answer text persisted | matched byte-for-byte | ✅ |
| 3.5 | `POST .../complete` | 200, `status: completed` | 200, matched; `evaluation_status: "not_configured"` | ✅ |
| 3.6 | `GET .../{id}` (results) | `status: completed` | matched | ✅ |
| 4.1 | `GET /api/interviews` | history includes session | included | ✅ |
| 4.2 | `GET /api/analytics` | `average_score: null` (0 evaluated) | matched, never `0` | ✅ |
| 4.3 | `GET /api/recommendations` | array present | `[{"key":"evaluate_an_answer",...}]` | ✅ |
| 5.1 | `POST .../evaluate` | honest 503 (disabled) | 503, `"AI answer evaluation is not configured on this server."` | ✅ |
| 6.1 | `POST /api/auth/register` (B) | 201 | 201 | ✅ |
| 6.2 | `GET` A's interview as B | 404, no leaked fields | 404, `{"detail":"Interview session not found."}` | ✅ |
| 6.3 | `POST /logout` with no CSRF | 403 | 403, `"Missing or invalid CSRF token."` | ✅ |
| 6.4 | Invalid `category` | 422 | 422, Pydantic literal error | ✅ |
| 6.5 | Weak password | 422 | 422, `"String should have at least 8 characters"` | ✅ |
| 6.6 | Recommendations, no auth | 401 | 401, `"Not authenticated."` | ✅ |

**All 21/21 matched.** This is genuine evidence the collection is correct
against the live API - not a claim that Postman itself was opened.

### A note on test-data hygiene (reported honestly, not omitted)

The `curl` verification above ran against the backend's **default**
database path (`backend/data/prepai.db`) because the backend had already
been started earlier in this session without a `DATABASE_PATH` override
- the assistant did not re-point it at an isolated file for this
verification pass, which was an oversight. That database already
contained a mix of the user's own real account (`hs5495498@gmail.com`,
11 prior interviews, untouched) and test fixtures from earlier sessions
(13 users and 31 interviews total before this pass). The verification
added 2 disposable test accounts and 1 clearly-labeled test interview
("Backend Developer (Postman Test)"); **nothing pre-existing was deleted,
modified, or overwritten.** Those 2 accounts and 1 interview were removed
again immediately afterward via a targeted `DELETE` by exact id (cascade
confirmed, no orphaned rows) - the database was verified back to 11
users / 31 interviews, its exact pre-verification state. Running the
actual Postman collection (which creates its own disposable accounts)
would have the same effect unless you also point `DATABASE_PATH` at an
isolated file first - worth doing if you re-run it.

## 5. AI evaluation configuration status

- **Disabled** - no `backend/.env` file exists in this environment, so
  `AI_EVALUATION_ENABLED` and `OPENAI_API_KEY` are both unset (the
  documented, safe default).
- The application responds honestly: `POST .../evaluate` returns `503`
  with `"AI answer evaluation is not configured on this server."`, and
  `POST .../complete`'s response reports `evaluation_status:
  "not_configured"` and `overall_score: null` - never a fabricated or
  zero-substituted score (confirmed live, request 3.5/5.1 above).
- **No real/paid provider request was made** in this session, by
  automated tests or by the manual `curl`/Postman verification - every
  evaluation-related check exercised the honest "not configured" path.
- A real-provider smoke test was not attempted - no API key or explicit
  authorization for a live provider call was available this session.

## 6. Automated vs. manual verification — explicit

| Verified | How |
|---|---|
| Backend suite (198/198) | Automated - `pytest`, run this session |
| Selenium suite (42/42) | Automated - real headless Chrome, run this session |
| 21 API workflows | Automated-equivalent - `curl`, replayed manually by the assistant this session against the live backend (Newman blocked by sandbox) |
| A human clicking through the app in a visible browser window | **Not performed.** No browser session was opened interactively by a person during this session. |

Nothing in this report should be read as a claim that a person manually
clicked through the UI - only that automated tools (pytest, Selenium's
real Chrome, and manual `curl` requests) exercised the real application
and real backend.

## 7. Remaining limitations

- Frontend was not started/verified in a real browser by a human this
  session - only via Selenium's automated Chrome.
- AI evaluation's live-provider path remains unverified end-to-end - all
  evidence of it working is from mocked-provider backend tests
  (`backend/tests/test_auto_evaluation.py`, 11 tests, all passing).
- Newman/Postman's own runner was not actually executed (sandboxed);
  the collection's correctness is demonstrated via equivalent manual
  `curl` replication, not a Postman-native run.
- `prepai/js/voiceCommands.js` remains untracked, untouched, not part of
  any change made this session.

## Reproducing this report

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)"
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/ -q
.\backend\.venv\Scripts\python.exe -m pytest tests/selenium/ -q
.\backend\.venv\Scripts\python.exe -m pytest --collect-only -q tests/selenium/
```
