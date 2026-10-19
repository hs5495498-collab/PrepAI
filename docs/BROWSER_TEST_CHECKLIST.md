# Manual Browser Testing Checklist

**Status: NOT YET PERFORMED.** Phase 11 explicitly left manual browser/DOM
testing outstanding, and Phase 12 has not performed it either - no browser
automation tool was used in this session, and no one has clicked through
the live UI yet. This checklist is the concrete list of what the user still
needs to do by hand (or via `/run` or browser automation in a future
session) before the application can be called manually verified end-to-end.

Every item includes the expected result. Check items off as you complete
them. Run the backend (`uvicorn main:app --reload`) and frontend (Live
Server on `127.0.0.1:5500`) first - see `LOCAL_SETUP_AND_DEMO.md`.

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
