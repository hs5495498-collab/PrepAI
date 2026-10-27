# Final Demonstration Plan (5-10 minutes)

A reproducible walkthrough using the actual application - no invented
features, no skipped steps. Do a dry run once before presenting live.
Updated 2026-10-27 to match the current dark navy/indigo/cyan design, the
account-vs-sample data separation on Dashboard/Analytics/Achievements,
and automatic AI evaluation on interview completion.

Prerequisites:
```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)\backend"
.\.venv\Scripts\python.exe -m uvicorn main:app --reload
```
Frontend served at `http://127.0.0.1:5500` (VS Code Live Server, rooted
at `prepai/` - see `.vscode/settings.json`, already configured). No
`backend/.env` file present means AI evaluation is off by default (free,
no cost) - see step 8 for what to say either way.

## Before you start

- [ ] Confirm `http://127.0.0.1:8000/health` returns `{"status":"ok"}`.
- [ ] Confirm `settings.html` shows "Backend connected."
- [ ] Use a **dedicated demo account**, not your personal one - e.g.
      `demo-<today's date>@example.com`.
- [ ] Decide in advance whether AI evaluation is enabled for this demo
      (costs a small real amount if so - see `backend/README.md`'s "AI
      answer evaluation" section) or left off (the honest "Not evaluated
      yet" / "Not configured" state, which is itself worth showing).

## Sequence

**1. Open PrepAI (15s)**
Click: open `index.html`.
Say: "This is PrepAI - a FastAPI backend behind a static HTML/CSS/JS
frontend, no framework, everything backed by a real SQLite database."

**2. Sign in with the test account (45s)**
Click: `settings.html` → Account section → register `demo-...@example.com`.
Say: "Logging in only changes one thing - interviews I create from now on
are tied to this account, readable only by me."

**3. Dashboard and the recommendation card (45s)**
Click: back to `index.html`.
Say: "'Your Account Overview' at the top is real data from my account -
right now it honestly says I haven't completed anything yet, because I
haven't. Below it, clearly labeled 'Sample Dashboard Preview', is
illustrative sample data shipped with the prototype - the two are never
blended into the same number."
Point out: the account section never shows a fabricated score.

**4. Open Practice Interview (15s)**
Click: `practice.html`.
Say: "The recommendation card above the setup form calls a real backend
endpoint (`GET /api/recommendations`) - a deterministic rule engine over
my own evaluated answers, not an AI call."

**5. Start a session (30s)**
Click: choose a role/category/difficulty → **Start Interview**.
Say: "This calls `POST /api/interviews`. Watch - the question stays
visible and doesn't disappear or reset, even if other data on the page
refreshes in the background."

**6. Answer and progress (45s)**
Type a real answer, click **Next Question** for 2-3 questions.
Say: "Each answer is submitted and persisted immediately
(`POST .../answers`) - refreshing the page would not lose it."

**7. Complete the interview (30s)**
Answer the last question, click **Finish Interview**, confirm the dialog.
Say: "This calls `POST .../complete`, which now also automatically
evaluates every answered question through the configured AI provider, if
one is configured - no need to click a separate button per question
first."

**8. Results and the genuine evaluation status (60s)**
Point out, depending on whether AI evaluation is enabled this session:
- **Disabled (default)**: "It honestly says 'Not evaluated yet' and
  explains AI evaluation isn't configured on this server - never a fake
  score, never 'Unsuccessful' just because evaluation is unavailable."
- **Enabled**: "`overall_score` here is the real mean of every evaluated
  question's score, computed server-side, never a word-count guess."
Click one question open to show the per-question Evaluate button /
breakdown either way.

**9. History (30s)**
Click: `history.html`.
Say: "'Your Account History' is the same real data, server-side. The
interview I just finished shows its true completion and evaluation
status - 'Completed' is never conflated with 'evaluated'."

**10. Analytics (30s)**
Click: `analytics.html`.
Say: "Same account/sample split as the Dashboard. 'Your Account
Analytics' excludes anything unevaluated from the average - a missing
score is never treated as zero."

**11. Achievements (30s)**
Click: `achievements.html`.
Say: "'First interview completed' can unlock just from completing one -
that's a real milestone regardless of evaluation. A score-based milestone
like 'Scored 80 or higher' never unlocks from an unevaluated interview's
placeholder number."

**12. Question variation (45s)**
Click: `practice.html` → start a **second** interview with the same
role/category/difficulty as step 5.
Say: "The question bank is shuffled per request and, for a signed-in
account, avoids repeating this account's own recently-asked questions in
this category/difficulty when enough alternatives exist - watch, these
are different questions from last time." (Point out the actual question
text differs.)

**13. Rule-based recommendations vs. AI evaluation (30s, no clicking)**
Say: "Two genuinely different things live in this app and it's worth
being precise about which is which: Recommendations (`backend/
recommendations.py`) are a plain deterministic rule engine - no AI call,
free, always available. AI evaluation (`backend/evaluation_provider.py`)
is a real OpenAI API call, off by default, costs a small real amount when
enabled, and is never silently substituted with a guess."

**14. Terminal test summary (30s)**
Show a real, just-run terminal window:
```powershell
cd "C:\Users\harsh\Downloads\prepai-redesign (1)"
.\backend\.venv\Scripts\python.exe -m pytest backend/tests/ -q
.\backend\.venv\Scripts\python.exe -m pytest tests/selenium/ -q
```
Say: "These are the actual current totals, run fresh, not a screenshot
from an earlier session - see `docs/TEST_EVIDENCE_2026-10-27.md` for the
full report."

## After the demo

- [ ] Log out the demo account (`settings.html` → Log Out).
- [ ] If you enabled AI evaluation, remember you were billed a small real
      amount - this is expected, not a bug.
