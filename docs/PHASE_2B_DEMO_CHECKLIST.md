# Phase 2B Demo Checklist — Final Readiness

**Status: automated coverage only, strengthened this phase. No human has
clicked through the live app in a visible browser window yet** - same
limitation as `docs/PHASE_2A_DEMO_CHECKLIST.md`: the Chrome
browser-extension tool was unavailable this session. Everything below
that says "verified" means verified by an automated headless-Chrome test
or by direct source inspection - never by a person operating the app.
Screenshots and automated browser checks are evidence of *that*, not of
manual human verification, and are never represented as the latter in
this document.

## Exact startup commands

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

```powershell
# separate terminal, from the frontend folder
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\prepai"
# Serve this folder at exactly http://127.0.0.1:5500 (VS Code "Live
# Server" extension, or any static server bound to that exact origin -
# required by the backend's CORS config in backend/main.py).
```

No `.env` file should exist for the standard demo - confirmed absent on
disk this phase. This keeps `AI_QUESTIONS_ENABLED`/`AI_EVALUATION_ENABLED`
both off, so every interview uses `question_source: "fixed"` at zero cost.

## Recommended presentation sequence

1. Open `index.html` - dashboard, existing "Start New Interview" entry point.
2. `settings.html` - register or log in (point out "Backend connected").
3. `practice.html` - show the **Recommended for You** card first: read its
   title/explanation/tags aloud, note it's a rule-based suggestion (or a
   generic starting point for a new account), not a trained AI model.
4. Click a category/difficulty change in the **plain setup form below the
   card** to show it's independent and still works exactly as before.
5. Click **Start Recommended Session** - land on question 1, labeled with
   the real category/difficulty/fixed-question-bank source.
6. Answer and advance through the interview; show the "Previous Question"
   answer-preservation/lock behavior if there's time.
7. Finish the interview (confirm dialog), land on `results.html`, expand a
   question to show the real submitted answer text (escaped, not raw HTML).
8. Return to `practice.html` - show the recommendation card's wording has
   changed now that the account has history (honest, not re-personalized
   with a fabricated score, since AI evaluation is off).
9. **Honest limitations, said out loud:** no manual click-through has been
   performed yet by a person; AI question generation/evaluation are off by
   default; voice/DSA/WebRTC/focus-monitoring remain unimplemented; the mic
   button is visual-only.

## Test commands and actual results (this phase)

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)"
backend\.venv\Scripts\python.exe -m pytest backend\tests -q
backend\.venv\Scripts\python.exe -m pytest tests\selenium -q
```

| Suite | Result |
|---|---|
| Backend pytest | **174/174 passed** |
| Selenium | **34/34 passed** (32 pre-existing + 2 new this phase), full suite re-run 3 times consecutively with 0 failures after the fix below |

## A genuine defect found and fixed this phase

**Rapid double-click on "Start Recommended Session" could create two real
interviews**, discovered by the new
`test_start_recommended_session_rapid_double_click_creates_only_one_interview`
test, which failed deterministically (5/5) when run in isolation.

Root cause (confirmed via direct instrumentation of the running page, not
guessed): the guard was the transient `creating` flag, which resets to
`false` the instant the in-flight request resolves. On this project's fast
localhost SQLite-backed backend, the **first** click's entire
request/response cycle can finish *faster* than the WebDriver round-trip
needed to even issue a second click - so by the time a fast second click
arrived, `creating` had already legitimately gone back to `false`, and the
(by then stale, hidden) card button's listener treated it as a brand-new,
legitimate request.

**Fix:** added a permanent `sessionStarted` latch in `prepai/js/pages.js`,
set once inside `beginSession()` and never reset, checked by both
`startFromCard()` (the recommendation card's buttons) and the original
`setupStart` click handler (the plain "Start Interview" button) before
either will ever call the create-interview API again. Verified: the
specific test now passes 6/6 in isolation (was 5/5 failing before the
fix), and the full Selenium suite passes 34/34 across 3 consecutive runs.

## Recommendation accuracy - verified this phase

- **Completing an interview changes the next recommendation**: re-verified
  via `test_logged_in_zero_history_shows_real_backend_text_and_updates_after_a_completed_interview`,
  which drives a real account from zero history ("Complete your first
  practice interview" - the backend's own text) through a full completed
  interview, then confirms the card now shows "Get AI feedback on a past
  answer" (also the backend's own, distinct text) - a real, data-driven
  change through the real API, not a frontend simulation.
- **Missing scores are not treated as zero / unattempted topics are not
  weaknesses**: already covered by
  `backend/tests/test_recommendations.py::test_missing_evaluations_are_not_treated_as_zero`
  and `test_category_never_mentioned_unless_it_has_evaluations` - both part
  of the 174 passing backend tests, re-run this phase, unchanged.
- **First-time users get a sensible baseline**: `showBaseline()` /
  `_no_history_recommendation()` path, confirmed via the zero-history test
  above and the pre-existing `test_no_history_produces_generic_beginner_recommendation`.
- **AI-disabled behavior is clearly communicated**: the card's "A
  rule-based suggestion... not a trained AI model" / "General starting
  point" copy, plus the pre-existing setup-panel notice about non-AI demo
  scoring and `sessionMode`'s "fixed question bank" labeling - all
  confirmed present via source inspection and exercised by passing tests.
- **Frontend handles the actual response schema without inventing
  fields**: `showFromRecommendations()` in `pages.js` reads only
  `title`, `explanation`, `reason`, `action`, `evidence`, `evidence_level`,
  `category`, `difficulty` - every one of these exists on
  `RecommendationOut` in `backend/schemas.py`; no field is invented, and
  `priority` (present on the schema) is simply unused by this UI, not
  misrepresented.

## UI quality - automated checks this phase (not manual)

New test `test_no_horizontal_overflow_at_demo_viewport_sizes` checks
`document.documentElement.scrollWidth` vs `clientWidth` on `practice.html`
at exactly **1366×768** and **390×844** - both pass with 0px of overflow,
and the recommendation card's Start button is confirmed displayed at both
sizes. This is an automated proxy for "no broken/overflowing layout," not
a substitute for a person actually looking at the rendered page.

## Manual checks: outstanding (all of them)

None of the 11 steps in `docs/PHASE_2A_DEMO_CHECKLIST.md`, nor the
presentation sequence above, have been performed by an actual person in a
visible browser as of this phase. This remains the single most important
thing to do before the live demonstration - ideally a full dry run using
the sequence above, by hand, start to finish.

## Known limitations to state honestly during the demo

- AI question generation and AI answer evaluation are off by default (no
  `.env` present) - every interview uses the fixed sample question bank.
- The microphone button on `practice.html` is visual-only; no real
  recording happens.
- Voice commands, a DSA coding round, WebRTC video interviews, and
  focus/camera monitoring are not implemented at all (not prototyped, not
  stubbed as "coming soon" anywhere in the UI).
- No rate limiting, no password reset/email verification, no structured
  logging - documented, pre-existing, out of scope for this phase.
- No real manual (human) click-through has been performed yet.
