# Deployment Readiness Assessment

**No deployment has happened.** This document assesses what the current
code supports and what is still missing before any real/public hosting -
it does not create hosting accounts, purchase services, or deploy anything.
Every item below was re-checked against the actual Phase 12 code, not
assumed from the Phase 11 report.

## Recommended architecture, if and when this is deployed

- **Static frontend** (`prepai/`): any static host that serves plain files
  over HTTPS (e.g. a static web host or CDN-backed bucket). No build step
  needed - the files can be uploaded as-is.
- **FastAPI backend** (`backend/`): a process host that can run
  `uvicorn`/`gunicorn` behind HTTPS, with persistent disk for the SQLite
  file (or a migration to PostgreSQL - see below) and a way to set
  environment variables (`OPENAI_API_KEY`, `AI_*_ENABLED`,
  `SESSION_COOKIE_SECURE`, etc.) outside of a committed file.
- These two pieces remain separately deployable, matching the current
  frontend/backend split - no architectural change is implied by hosting
  them.

This is a recommendation for *if* deployment happens later, not an action
taken now.

## Item-by-item status (re-verified this phase)

| Item | Status found in Phase 12 | Detail |
|---|---|---|
| Authentication rate limiting | **Still not implemented.** | No rate-limiting middleware or login-attempt counter exists anywhere in `backend/`. A grep for `limiter`/`throttle`/`rate` across `backend/*.py` found nothing. |
| `SESSION_COOKIE_SECURE` | **Still defaults to `false`; code path confirmed correct for HTTPS when set.** | `auth.py`'s `session_cookie_secure()` reads `SESSION_COOKIE_SECURE` from the environment, defaulting to `false`. `main.py`'s `_set_auth_cookies` passes this value straight to `secure=` on both cookies. Setting the env var to `true` in a real HTTPS environment is sufficient - no code change needed, just correct configuration at deploy time. |
| CORS origins | **Still hardcoded to one local dev origin.** | `main.py`: `allow_origins=["http://127.0.0.1:5500"]`. A real deployment must change this to the real frontend domain(s) before anything works cross-origin - confirmed by reading the exact line, not assumed. |
| CSRF protection | **Implemented and verified live this phase.** | Double-submit cookie pattern (`auth.py`, `main.py`'s `_require_csrf`). Re-verified live in Phase 12: an authenticated request without `X-CSRF-Token` was rejected with `403` against a freshly started server (see the Phase 12 final report for the exact PID/command used). |
| SQLite vs. concurrent-write workloads | **Still a real constraint, unchanged.** | `db.py` opens a brand-new `sqlite3` connection per call with no pooling; SQLite serializes writers. Fine at prototype/single-user scale, not verified under concurrent load. |
| Password reset / email verification | **Still absent.** | No route, module, or email-sending dependency exists anywhere in `backend/` (grep for `reset`/`verify`/`smtp`/`email` found no implementation, only comments noting the gap). |
| Structured logging / monitoring | **Still minimal.** | The backend has no `logging.`/`print(` calls in any `.py` file (re-confirmed by grep this phase) - the global exception handler returns a safe generic message but records nothing for an operator to see. |
| Manual browser testing | **Still outstanding.** | See `BROWSER_TEST_CHECKLIST.md` - not performed in Phase 12 either (no browser automation was used this session). |

None of the above required changing in Phase 12 because each is a
deployment-time configuration or a feature gap, not a defect in local/
prototype behavior - re-architecting authentication, migrating databases,
or adding logging infrastructure "to finish the phase" was explicitly out
of scope per this phase's instructions.

## Small, justified fixes made this phase

**None required.** Phase 12's code-level verification (full test suite,
live CORS/CSRF/ownership/oversized-answer checks against a freshly started
server - see the final report) found the Phase 11 fixes still correctly in
place, and no new defect was found that warranted a small, safe, backward-
compatible patch. No code was changed in Phase 12.

## Remaining prerequisites before any real deployment

In rough priority order:

1. **Set real production environment variables** - a real `CORS` origin
   list, `SESSION_COOKIE_SECURE=true`, and (only if desired) real
   `OPENAI_API_KEY`/`AI_*_ENABLED` values - via the hosting platform's
   secret/environment configuration, never committed to `.env`.
2. **Decide on SQLite vs. PostgreSQL** based on expected concurrent write
   load. Single-user demo/prototype traffic can likely stay on SQLite with
   a single worker process; anything with real concurrent users should
   migrate (see `ARCHITECTURE.md`'s database section for what that
   migration actually involves).
3. **Add authentication rate limiting** (e.g. a per-IP/per-email login
   attempt counter) before exposing registration/login publicly.
4. **Decide whether password reset/email verification are required** for
   the target audience - currently entirely absent.
5. **Add structured logging** for at least failed logins, AI provider
   errors, and unhandled 500s, so an operator has something to alert on.
6. **Add database backups** on a schedule appropriate to the hosting
   platform (see `ARCHITECTURE.md` for the manual backup/restore commands
   this project already documents).
7. Run `uvicorn`/`gunicorn` **without `--reload`**, behind a real process
   manager, with multiple workers only once the database layer supports
   concurrent writers (see item 2) - running multiple workers against the
   current unpooled SQLite setup risks write contention.
8. Complete the manual browser testing checklist (`BROWSER_TEST_CHECKLIST.md`)
   at least once against a close-to-production configuration before calling
   the application end-to-end verified.

## What was explicitly not done

- No hosting account was created.
- No payment information was entered anywhere.
- Nothing was deployed publicly or privately to any external host.
- No pricing research was performed this phase (the one pricing figure in
  this repository, OpenAI's `gpt-4o-mini` estimate in `backend/README.md`,
  predates Phase 12 and is explicitly marked there as an estimate, not a
  verified current quote - it was not re-verified in Phase 12 and should
  be checked at `platform.openai.com/pricing` before relying on it).
