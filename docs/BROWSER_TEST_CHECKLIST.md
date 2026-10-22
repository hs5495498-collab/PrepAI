# Manual Browser Testing Checklist

**Status: manual click-through still NOT performed.** No one has clicked
through the live UI by hand in any phase, including this one - the items
below remain unchecked for that reason. A Phase 0/1 automated-verification
pass did, however, add real Selenium browser coverage (`tests/selenium/`,
27 tests, headless Chrome, run via
`backend\.venv\Scripts\python.exe -m pytest tests\selenium -v`) for several
of the workflows this checklist describes. See "Automated coverage" just
below for exactly which items that satisfies - automated coverage is a
different, narrower kind of evidence than a human manually clicking through
the real browser UI, and the two are never merged into one claim here.

Every item includes the expected result. Check items off as you complete
them by hand. Run the backend (`uvicorn main:app --reload`) and frontend
(Live Server on `127.0.0.1:5500`) first - see `LOCAL_SETUP_AND_DEMO.md`.

## Automated coverage (Selenium, Phase 0/1 of this audit cycle)

These specific behaviors are exercised by an automated, headless browser
test and pass reproducibly (confirmed by running the suite 4 times in a
row with 0 failures) - this is **automated-test verification, not manual
verification**, and the checkboxes below are intentionally left unchecked:

| Checklist item | Automated by |
|---|---|
| Register, duplicate email rejected, malformed email rejected, wrong password rejected, login, logout, session persists on refresh | `TestAccountAndInterviewFlow::test_04`-`test_10` |
| Topbar shows "Log In" / signed-in email on every `js/api.js` page | `test_03b`, `test_10b`, `test_dashboard_offers_a_clear_login_link_when_logged_out` |
| Backend-connected indicator | `test_03_backend_status_indicator_shows_connected` |
| Start interview, distinct question per step, live question counter | `test_11_start_interview`, `test_12_answer_and_navigate_all_questions` |
| 15-question interview has 15 distinct questions (fixed bank and offline-demo mirror) | `test_fifteen_question_interview_has_no_duplicate_questions`, `test_offline_demo_fifteen_questions_has_no_duplicates` |
| Blank-answer rejected with a visible hint | `test_blank_answer_rejected_during_interview` |
| Going back preserves a typed/submitted answer, and the answer box locks (matches the backend's duplicate-answer `409`) | `test_previous_question_answer_is_preserved_and_locked_after_submit` (new) |
| Interview completion reaches `results.html`, demo score shown and labeled "(demo)" | `test_13_interview_completion_shows_results`, offline-mode tests |
| Typed HTML in an answer renders as literal text, never executes/renders as markup | `test_13_interview_completion_shows_results` |
| Account history shows a new entry; local-browser-history section stays present and separate | `test_14_history_shows_new_account_entry`, `test_history_logged_out_shows_local_section_only` |
| Analytics and recommendations sections render (non-empty) for a logged-in account | `test_15_analytics_and_recommendations_render` |
| Offline demo mode completes a full interview with the backend stopped | `test_offline_demo_mode_completes_without_backend` |
| **Cross-account isolation**: account B cannot open account A's interview via its own history-page link (gets the same "not found" notice), and account B's own history never mentions account A's interview | `TestCrossAccountIsolation` (new, two real registered accounts, real cookies, a real `session_id` taken from the UI's own link - not a hand-built URL) |

**Still only possible by hand, or explicitly out of scope for automation**
(unchanged by this phase): the AI-evaluation enabled/disabled/failure cases
(would require a real `OPENAI_API_KEY` and real cost - never run by an
automated suite per this project's rules), oversized-answer (10,001+ char)
rejection via the UI (covered at the API level only, in
`backend/tests/test_api.py`), mid-interview refresh behavior, backend-restart
persistence via the UI (covered at the storage layer only, in
`backend/tests/test_storage.py`), and literally watching the Network tab.

## Registration, login, logout

- [ ] Register a new account with a valid email and an 8+ character
      password on `settings.html`. **Expected:** account created, UI shows
      your email and a Log Out button, no page reload needed.
- [ ] Try registering the same email again. **Expected:** a clear inline
      error (already registered), not a silent failure or page crash.
- [ ] Try registering with a malformed email (`not-an-email`). **Expected:**
      a clear validation error before/instead of a network round trip.
- [ ] Log out. **Expected:** UI returns to the logged-out state (email/
      password fields and Create Account/Log In buttons).
- [ ] Log back in with the same credentials. **Expected:** success, same
      logged-in UI as after registration.
- [ ] Log in with a wrong password. **Expected:** a generic "incorrect
      email or password" message - not a hint about which part was wrong.

## Backend connection status

- [ ] With the backend running, open `settings.html`. **Expected:** a
      "Backend connected" indicator.
- [ ] Stop the backend, reload `settings.html`. **Expected:** a "Backend
      unavailable" indicator, no uncaught JS errors in the console.

## Interview creation and navigation

- [ ] On `practice.html`, pick a role/category/difficulty/question count and
      click Start Interview. **Expected:** the first question appears, a
      live question counter, and (if visible in the UI) `question_source`
      shown as "fixed" with no `.env` configured.
- [ ] Navigate forward through all questions using the provided controls.
      **Expected:** each question's text is distinct and matches the
      selected category/difficulty pool.
- [ ] Try to go past the last question without answering it. **Expected:**
      the app either blocks this or marks the question unanswered -
      confirm which, and that it matches the rest of the UI's labeling
      (completed vs. incomplete vs. missed).

## Answer preservation and submission

- [ ] Type an answer, move to the next question, then use the UI's "back"
      control (if present) to return to the previous question. **Expected:**
      your typed answer is still visible (not cleared).
- [ ] Submit an answer, then try to edit and resubmit it for the same
      question (e.g. by going back). **Expected:** the answer box is locked
      for an already-submitted question - matches the backend's `409` on a
      duplicate answer.
- [ ] Open browser dev tools → Network tab while answering. **Expected:** a
      `POST /api/interviews/{id}/answers` call per answered question, with
      `credentials: include` and (if logged in) an `X-CSRF-Token` header.

## Interview completion

- [ ] Answer every question, then click Finish Interview. **Expected:**
      navigation to `results.html`, a `POST /api/interviews/{id}/complete`
      call in the Network tab, and the session's status becomes
      "completed."
- [ ] Try to submit another answer to a completed session (e.g. by
      replaying the request in dev tools, or going back if the UI allows
      it). **Expected:** rejected (`409`), not silently accepted.

## Results rendering

- [ ] On `results.html` after finishing, confirm the demo score is shown
      and labeled "(demo)". **Expected:** score is a plausible number
      derived from your actual answers, never blank or `NaN`.
- [ ] Confirm every question and your submitted answer text is displayed
      correctly (no HTML injection from your own typed text - type `<b>test</b>`
      as an answer and confirm it renders as literal text, not bold).

## AI evaluation - disabled state (default)

- [ ] With `AI_EVALUATION_ENABLED` unset, click "Evaluate with AI" on a
      completed, backend-sourced result. **Expected:** a clear "not
      configured" message, no score fabricated, button re-enables.

## AI evaluation - enabled, success case (deliberate, costs real money)

- [ ] Set `AI_EVALUATION_ENABLED=true` and a real `OPENAI_API_KEY` in
      `backend/.env`, restart the backend, then click "Evaluate with AI" on
      one answered question. **Expected:** a score breakdown (4 dimensions
      + total), strengths/weaknesses/suggestions, and the `note` disclaimer
      text, all rendered in the UI. **Remember to turn the flag back off
      afterward if you don't want further clicks to cost money.**
- [ ] Click "Evaluate with AI" again on the same question. **Expected:**
      the same stored result reappears instantly - no second provider call
      (check the Network tab timing, or your OpenAI usage dashboard, to
      confirm no second charge).

## AI evaluation - enabled, failure case

- [ ] Temporarily set an invalid `OPENAI_API_KEY` (still with
      `AI_EVALUATION_ENABLED=true`), restart the backend, and click
      "Evaluate with AI" on a fresh (never-evaluated) question. **Expected:**
      a clear error message (not a blank/broken UI state), and nothing
      saved - retrying with a valid key afterward should still work on that
      same question.

## History and persistent detail links

- [ ] While logged in, complete an interview, then open `history.html`.
      **Expected:** it appears in "Your Account History" with correct
      role/category/status.
- [ ] Click into that history row's detail link
      (`results.html?session=<id>`). **Expected:** the same results page,
      fetched fresh from the backend (not from `localStorage`).
- [ ] Confirm the separate "Local Browser History (This Device Only)" table
      below it still shows the original sample/offline data, clearly
      labeled, and is not mixed with account history rows.

## Analytics calculations and empty states

- [ ] On a brand-new account with zero completed interviews, open
      `analytics.html`. **Expected:** "Your Account Analytics" shows an
      honest empty/zero-data state - never fabricated numbers or a blank
      crash.
- [ ] After completing and evaluating at least 2 answers, reload
      `analytics.html`. **Expected:** average/highest/most-recent scores,
      a category/dimension breakdown, and a progress chart all populate
      with numbers that look consistent with what you actually submitted.

## Personalized recommendations

- [ ] On a brand-new account, check the "Personalized Recommendations"
      section. **Expected:** a generic "complete your first interview"
      suggestion, not an error.
- [ ] After completing interviews but with zero evaluated answers, reload.
      **Expected:** a different generic message about evaluating an answer
      - distinct wording from the "no interviews" case.
- [ ] After a few evaluated answers in one category score consistently low
      (below 60), reload. **Expected:** a specific "practise more X
      questions" recommendation citing your real average score.

## Offline demo mode

- [ ] With the backend stopped, start an interview on `practice.html`.
      **Expected:** a clear "backend unreachable" state and a "Continue in
      Offline Demo Mode" button - not a silent hang or crash.
- [ ] Click it and complete a full interview. **Expected:** it completes
      using fixed sample questions, and the resulting attempt's `source` is
      recorded as `offline` (visible in how `results.html` / history
      describes this attempt vs. a backend-sourced one).

## Refresh and backend-restart persistence

- [ ] Mid-interview, refresh the page. **Expected:** the live in-progress
      UI state is lost (this is a documented, known limitation - there is
      no resume-after-refresh feature), but the data already submitted to
      the backend before the refresh is not lost (confirm via
      `GET /api/interviews/{id}` in `/docs`, or via account history once
      the interview is later marked complete through some other means).
- [ ] Complete an interview, restart the backend process, then reopen
      `history.html`. **Expected:** the interview still appears - proof
      the SQLite file, not memory, is the real store.

## Error handling and recovery

- [ ] Submit a 10,001+ character answer (e.g. paste a very long string).
      **Expected:** rejected with a clear error, not a silent truncation or
      a crash.
- [ ] Submit a blank/whitespace-only answer. **Expected:** rejected with a
      clear "answer must not be blank" style error.
- [ ] Trigger a backend 500 if possible (hard to do without breaking
      something on purpose - optional) and confirm the frontend shows a
      generic error rather than exposing a raw stack trace.

## Cross-account privacy

- [ ] Using two separate browser profiles (see `LOCAL_SETUP_AND_DEMO.md`
      §12), log in as two different accounts. Create an interview as
      account A, then try to open its `?session=` URL and find it in
      account B's history. **Expected:** not visible, not listed, and
      directly requesting it returns the same "not found" result a
      nonexistent session ID would.
- [ ] Confirm account B's analytics/recommendations never show any of
      account A's scores (e.g. a brand-new account B should show an empty
      state even if account A has rich history).

## Legacy localStorage history

- [ ] Clear `backend` connectivity or simply look at `history.html` without
      ever logging in. **Expected:** the "Local Browser History (This
      Device Only)" table still works exactly as it did before accounts
      existed, using only sample/offline `localStorage` data, with no
      reference to any account.
- [ ] Confirm an old attempt made before any account existed (or made
      entirely offline) does **not** show an "Evaluate with AI" button on
      its results page - documented limitation, since there's no backend
      session for it to evaluate against.
