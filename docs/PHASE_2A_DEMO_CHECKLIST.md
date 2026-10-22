# Phase 2A Demo Checklist — Personalized Practice Recommendations

**Status: automated coverage only. No human has clicked through this by
hand in a real, visible browser window yet** - the Chrome browser-extension
tool was unavailable in this session (not connected), so "manual
verification" below was performed via headless-Chrome diagnostic scripts
driven by this session, not by a person. That is a form of automated,
reproducible verification (DOM-state inspection + screenshots), but it is
**not** the same as a human manually operating the app, and it is not
claimed as such anywhere in this document. True manual click-through
remains outstanding - see `docs/BROWSER_TEST_CHECKLIST.md`.

## What to run first

```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.venv\Scripts\Activate.ps1
uvicorn main:app --reload
```

```powershell
# separate terminal, from the frontend folder
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\prepai"
# Open practice.html (or any page) with VS Code's "Live Server" extension,
# or any static server bound to exactly http://127.0.0.1:5500
```

No `.env` file should be present for the standard demo (keeps AI features
off, zero cost, `question_source: "fixed"` throughout).

## The 11 manual steps (to be performed by a person before the live demo)

1. **Log in.** Open `settings.html`, register or log in with a real
   account. **Automated-equivalent check:** `TestAccountAndInterviewFlow`
   (existing, Phase 0/1) and the new `register()` helper used throughout
   `TestPracticeRecommendation` (`tests/selenium/test_e2e_flows.py`) do
   this on every run. **Not yet performed by hand this phase.**
2. **Open Practice Interview.** Confirm the "Recommended for You" card
   appears above "Set Up Your Practice Interview" with a loading state
   that resolves within ~1 second. **Automated-equivalent check:** every
   test in `TestPracticeRecommendation` does this first.
   **Not yet performed by hand.**
3. **Read the recommended session and its explanation.** For a brand-new
   account, confirm the card shows "Complete your first practice
   interview" with the real explanation text from
   `backend/recommendations.py`'s `_no_history_recommendation()` - not
   frontend-invented copy. **Automated-equivalent check:**
   `test_logged_in_zero_history_shows_real_backend_text_and_updates_after_a_completed_interview`.
   **Not yet performed by hand.**
4. **Change an available session option.** Scroll to "Set Up Your
   Practice Interview" below the card and change the category/difficulty/
   question count manually, confirming the form is fully independent and
   still works exactly as before. **Not automated as a dedicated test this
   phase** (the underlying form was unchanged and is covered by the
   existing `test_11`-`test_12` flow) - **not yet performed by hand.**
5. **Start the recommended session.** Click "Start Recommended Session"
   and confirm it lands on a real question (not a placeholder), labeled
   with the correct category/difficulty, sourced from the fixed question
   bank (no `.env` present). **Automated-equivalent check:**
   `test_logged_out_shows_generic_baseline_and_can_start_a_real_interview`
   and others. Also directly DOM-state-verified in this session via a
   headless diagnostic script (not committed to the suite) that confirmed
   the setup→session transition completes in ~0.1-0.2s with correct
   `question_source` and category/difficulty labeling.
   **Not yet performed by hand.**
6. **Submit at least one answer.** Confirm it's accepted and the counter
   advances. **Automated-equivalent check:** existing `test_12` flow,
   reused end-to-end by the new recommendation tests. **Not yet performed
   by hand.**
7. **Complete the interview.** Finish all questions, confirm the native
   "Finish Interview?" `confirm()` dialog, and reach `results.html`.
   **Automated-equivalent check:**
   `test_logged_in_zero_history_shows_real_backend_text_and_updates_after_a_completed_interview`
   drives a full 5-question interview to completion. **Not yet performed
   by hand.**
8. **Inspect the results.** Confirm the demo score and labeled "(demo)"
   notice appear, and your submitted answers render as literal text.
   **Automated-equivalent check:** existing `test_13`. **Not yet performed
   by hand.**
9. **Return to practice and inspect the next recommendation.** Confirm the
   card's wording changed now that the account has one completed interview
   (it should say "Get AI feedback on a past answer" instead of "Complete
   your first practice interview" - still zero evaluations since AI is
   off, so neither message is fabricated). **Automated-equivalent check:**
   same test as step 3/7, final assertions. **Not yet performed by hand.**
10. **Verify a first-time or empty-history state if practical.** Use a
    second, freshly registered account and confirm it independently shows
    the zero-history baseline, with no leakage from the first account's
    data. **Automated-equivalent check:**
    `TestCrossAccountIsolation` (Phase 0/1, unchanged) plus every
    `TestPracticeRecommendation` test registering its own fresh account.
    **Not yet performed by hand.**
11. **Verify a visible error state if the backend is unavailable.** Stop
    the backend, reload `practice.html`, and confirm the card shows
    "Could not load your personalized recommendation — make sure the
    backend is running." with a working "Try again" button, and that
    `#setup` still renders normally (no uncaught JS errors in the
    console). **Automated-equivalent check:**
    `test_recommendation_card_shows_error_and_retry_when_backend_unavailable`.
    **Not yet performed by hand.**

## Automated test coverage summary (this phase)

New Selenium tests in `tests/selenium/test_e2e_flows.py::TestPracticeRecommendation`
(5 tests, all passing, re-run 3 times consecutively with 0 failures):

| Test | Covers |
|---|---|
| `test_logged_out_shows_generic_baseline_and_can_start_a_real_interview` | Logged-out baseline card + real interview creation |
| `test_logged_in_zero_history_shows_real_backend_text_and_updates_after_a_completed_interview` | Real backend-sourced copy for zero-history and post-completion states |
| `test_start_recommended_session_rapid_double_click_creates_only_one_interview` | Duplicate-submission prevention |
| `test_recommendation_card_shows_error_and_retry_when_backend_unavailable` | API-failure/error/retry state |
| `test_recommendation_card_renders_and_starts_a_session_at_mobile_width` | Responsive layout at 390×844 |

Pre-existing backend tests already cover the recommendation *logic* this
card consumes (not duplicated by new tests): `backend/tests/test_recommendations.py`
(17 tests - baseline/weak/strong/inconsistent/missing-data-not-zero/
determinism) and `backend/tests/test_recommendations_api.py` (7 tests -
auth required, cross-account isolation, anonymous exclusion).

Full suite results after all Phase 2A changes: **backend 174/174 passed**,
**Selenium 32/32 passed** (27 pre-existing + 5 new), Selenium suite re-run
3 times consecutively with 0 failures.

## Known gap

No real manual (human, visible-browser) click-through of this checklist
has been performed as of this phase. The headless-Chrome diagnostic
screenshots taken during development (not part of the committed test
suite) visually confirmed the desktop and mobile layouts look correct and
cohesive with the rest of the app, but this is not a substitute for an
actual person clicking through before the live demonstration.
