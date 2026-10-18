# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PrepAI — a static interview-practice dashboard prototype. Plain HTML/CSS/JS only: no build step, no package manager, no framework, no bundler, no CDN scripts except the Inter Google Font (which degrades to system fonts if offline).

## Running / testing

There is no build or test tooling. To work on the app, open any `.html` file directly in a browser (e.g. `index.html`), or serve the folder with any static file server. There is no lint/build/test command to run — verify changes by loading the page in a browser.

## Architecture

Every screen is a standalone HTML file that loads these scripts in a fixed order:

```
js/icons.js → js/data.js → js/chart.js → [js/api.js] → js/pages.js → js/app.js
```

`js/api.js` is optional and only included on pages that actually talk to the backend (currently `practice.html` and `settings.html`). Pages that don't need it keep the original five-script list.

- **`js/data.js`** — the single source of truth. Defines `window.PREP`, with the sample dataset (`attempts`, `skills`, `achievements`, `actions`, `feedback`, `details`, `bank`) and derived helpers (`completed()`, `result()`, `changeFor()`, `achievementState()`, etc). Every number rendered anywhere in the UI is computed from this object — there is no other data source. It also loads/persists real completed demo attempts (`P.addDemoAttempt`, see "Data model notes" below).
- **`js/api.js`** — `window.PREP_API`: a small fetch wrapper for the FastAPI backend (`backend/`), pointed at `http://127.0.0.1:8000`. Every call resolves (never rejects) to `{ ok, status, data }`; `status === 0` means a network failure/timeout rather than a real HTTP response, so callers can tell "backend unreachable" apart from a real 4xx/5xx. This is the only place the backend URL is hardcoded.
- **`js/pages.js`** — defines `window.PREP_PAGES`, a map of page-name → render function (`dashboard`, `practice`, `history`, `analytics`, `achievements`, `plan`, `results`, `settings`). Each function reads from `window.PREP`, builds HTML strings, and injects them into the current page's DOM. No templating engine — just string concatenation with a local `esc()` helper for untrusted text.
- **`js/app.js`** — the app shell. On `DOMContentLoaded` it: applies saved display settings, builds and injects the sidebar `<nav>` (the `NAV` array is the single list of screens/labels/icons), wires the mobile menu, hydrates inline icons, then looks up `body[data-page]` and invokes the matching function from `window.PREP_PAGES`.
- **`js/chart.js`** — `window.createChart(container, options)`: a dependency-free inline-SVG line chart with trend line, markers, and tooltips. Returns `{ update(partial) }` so pages can redraw on filter changes (see `pages.analytics`).
- **`js/icons.js`** — `window.icon(name, size)` returns inline SVG markup; `window.hydrateIcons(root)` fills any `[data-icon]` element.
- **`css/styles.css`** — the entire design system (colors, type, components, responsive rules) in one file. No CSS preprocessor.

### Page wiring convention

Each HTML file's `<body>` carries two data attributes that drive `app.js`:
- `data-page="<name>"` — selects which function in `window.PREP_PAGES` to run.
- `data-nav="<file>.html"` — marks the matching sidebar link `aria-current="page"`.

When adding a new screen: create the HTML file with these attributes and the script tags (add `js/api.js` only if that page calls the backend), add an entry to the `NAV` array in `js/app.js`, and add a render function to `js/pages.js` under the matching key.

### Data model notes

- An attempt's `status` is one of `completed | incomplete | missed`. Only `completed` attempts have a `score`; incomplete/missed attempts are never scored (by design, not a bug).
- `P.ref` (in `data.js`) is the latest attempt's date, and all "last N days" range filters (history, analytics) count backwards from it rather than from `Date.now()` — the prototype's dataset is meant to look current relative to itself.
- Settings (`settings.html`) persist to `localStorage` under `prepai.settings`; `window.PREP_SETTINGS()` reads them and `window.applyDisplaySettings()` applies text-size/reduce-motion globally.
- Completed/incomplete practice attempts persist to `localStorage` under `prepai.demoAttempts` via `P.addDemoAttempt`/`loadDemoAttempts` in `data.js`. A completed attempt's `source` field is `'backend'` if its answers were actually submitted to the FastAPI backend during that session, or `'offline'` if the session ran entirely in the browser (backend unavailable, or the user chose "Continue in Offline Demo Mode"). The backend itself only keeps sessions in memory — nothing survives a backend restart, so `localStorage` is the only thing that persists across browser sessions, and it is not a substitute for a real database.

### Known prototype limitations (see README.md)

- The microphone/waveform UI in `practice.html` is visual only — no real recording. Hook up `MediaRecorder`/speech-to-text inside `setRecording()` in `pages.js`.
- Interview *questions* can be AI-generated (see `backend/ai_provider.py`), but this is off by default and requires the user to configure their own API key in `backend/.env` — see `backend/README.md`. There is still no AI *answer evaluation* anywhere: all scores shown (backend-connected or offline, AI-generated questions or fixed) are the same non-AI word-count heuristic from `demoScore()` in `pages.js`, always labeled "(demo)".
- A session's `question_source` (`"ai"` or `"fixed"`) is shown live during the interview (next to the question counter) but is not persisted into `localStorage` history — only the existing `source` (`backend`/`offline`) field is.
- The backend (`backend/`) has no database — interview sessions are in-memory only and are lost on restart. See `backend/README.md`.
