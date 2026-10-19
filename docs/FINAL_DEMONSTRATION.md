# Final Demonstration Plan (5-10 minutes)

A reproducible walkthrough using the actual application - no invented
features, no skipped steps. Do a dry run once before presenting live.
Prerequisites: backend running (`uvicorn main:app --reload` from
`backend\.venv`), frontend served at `http://127.0.0.1:5500` (see
`LOCAL_SETUP_AND_DEMO.md`), no `.env` file present (AI features off,
default/free demo).

## Before you start

- [ ] Confirm `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
- [ ] Confirm `settings.html` shows "Backend connected."
- [ ] Have two browser profiles/windows ready if you plan to demo account
      isolation (one normal, one Incognito/InPrivate works fine).
- [ ] Decide in advance whether you will enable AI evaluation live (costs a
      small real amount - see step 7) or skip straight to the safe
      alternative.

## Sequence

**1. Open the dashboard (30s)**
Click: open `index.html`.
Say: "This is PrepAI, an interview-practice app with a FastAPI backend
behind this static frontend. Everything you'll see is backed by a real,
persisted SQLite database, not just mock data on this one screen."
Capture: a screenshot of the dashboard.

**2. Register an account (45s)**
Click: `settings.html` → Account section → enter an email/password →
Create Account.
Say: "Accounts are optional throughout this app, but logging in ties
future interviews to this account so I can show history and analytics
later."
Capture: the logged-in state showing your email.

**3. Start and complete a short interview (90s)**
Click: `practice.html` → pick Technical / Easy / 2 questions → Start
Interview → answer both questions → Finish Interview.
Say while answering: "Each answer is submitted to the backend as I go -
you can see that in the Network tab if you want proof it's a real API
call, not just local state." (Optionally open dev tools and point at the
`POST /api/interviews/{id}/answers` calls.)
Capture: the results page right after finishing.

**4. Show persistent history (45s)**
Click: `history.html`.
Say: "This 'Your Account History' section is a real database query,
`GET /api/interviews`, scoped to my account only. Below it, completely
separate, is the original local-browser sample history - the two are
never mixed."
Capture: both sections visible on one screen.

**5. Demonstrate account isolation (60s)**
Switch to the second browser profile/window, log in as (or register) a
*different* account, and open `history.html` there.
Say: "This is a different account - notice it has no visibility into the
interview I just created. If I try to open that same results link
directly..." (paste the first account's `results.html?session=...` URL).
"...it returns the same 'not found' response a made-up session ID would -
it never confirms the other interview exists at all."
Capture: the empty/absent result on the second account.

**6. Show analytics and recommendations (60s)**
Switch back to the first account, open `analytics.html`.
Say: "With only one ungraded interview, these sections honestly show 'not
enough data yet' rather than fabricating numbers - that's deliberate."
If you have time and a second account/history with evaluated answers
prepared ahead of time, switch to show a populated version instead:
"...and here's the same page with enough history to show a real score
breakdown, strongest/weakest dimension, and a specific recommendation
citing my own average score as evidence."
Capture: both the empty-state and (if shown) populated versions.

**7. Show AI evaluation safely (60-90s)**

*Safe default (no cost):* On the results page, click "Evaluate with AI."
Say: "This feature is off by default - notice it gives a clear 'not
configured' message instead of pretending to score anything. Enabling it
requires deliberately setting two environment variables and restarting
the server - it can never turn on by accident."

*Optional live version (costs a small real amount):* If you've pre-staged
`AI_EVALUATION_ENABLED=true` and a real key in `backend/.env` and
restarted the backend beforehand, click "Evaluate with AI" here instead
and show the real score breakdown and written feedback.
Say: "This made one real request to OpenAI's API just now, and the
backend computes the final score itself from four separate dimension
scores - it never just trusts whatever total the model reports." Click
it again to show the *second* click returns instantly with no new charge.

**8. Fallback if the network or AI provider is unavailable (30s, only if
needed)**
Say: "If the AI provider or network were unavailable right now, this
button would show a clear error instead of a fake score - and separately,
if the backend itself were down, the whole interview flow has an offline
fallback." (Optionally actually demonstrate: stop the backend, try to
start a new interview on `practice.html`, show "Continue in Offline Demo
Mode," and complete one short interview that way.)

**9. Honest limitations (30s)**
Say, directly: "A few things are intentionally not built yet: there's no
password reset or email verification, no rate limiting on login attempts,
and manual browser/DOM testing is still a documented outstanding task
rather than something I'm claiming is done. The full list is in
`docs/DEPLOYMENT_READINESS.md`."

## Evidence to capture during a real run

- Screenshot of the dashboard.
- Screenshot of the completed interview's results page.
- Screenshot of "Your Account History" with at least one real entry.
- Screenshot showing the second account's empty/absent view of the first
  account's interview (proves isolation).
- Screenshot of the analytics page (empty-state and, if staged, populated).
- Screenshot of either the "AI evaluation not configured" message or a
  real evaluation result, matching whichever path you chose in step 7.
- (Optional) Network tab screenshot showing a real `POST` call with
  `credentials: include` and an `X-CSRF-Token` header.

## Timing budget

| Step | Time |
|---|---|
| 1-2 (open + register) | 1:15 |
| 3 (interview) | 1:30 |
| 4 (history) | 0:45 |
| 5 (isolation) | 1:00 |
| 6 (analytics/recommendations) | 1:00 |
| 7 (AI evaluation) | 1:30 |
| 8 (fallback, optional) | 0:30 |
| 9 (limitations) | 0:30 |
| **Total** | **~8 minutes** (fits the 5-10 minute target; skip step 8 to tighten it to ~7:30) |
