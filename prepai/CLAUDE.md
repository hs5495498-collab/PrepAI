# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

PrepAI — a static interview-practice dashboard prototype. Plain HTML/CSS/JS only: no build step, no package manager, no framework, no bundler, no CDN scripts except the Inter Google Font (which degrades to system fonts if offline).

## Running / testing

There is no build or test tooling. To work on the app, open any `.html` file directly in a browser (e.g. `index.html`), or serve the folder with any static file server. There is no lint/build/test command to run — verify changes by loading the page in a browser.

## Architecture

Every screen is a standalone HTML file that loads the same five scripts in this fixed order:

```
js/icons.js  → js/data.js → js/chart.js → js/pages.js → js/app.js
```

- **`js/data.js`** — the single source of truth. Defines `window.PREP`, with the sample dataset (`attempts`, `skills`, `achievements`, `actions`, `feedback`, `details`, `bank`) and derived helpers (`completed()`, `result()`, `changeFor()`, `achievementState()`, etc). Every number rendered anywhere in the UI is computed from this object — there is no other data source. To wire up a real backend, replace the contents of this file and keep the same shape/helpers.
- **`js/pages.js`** — defines `window.PREP_PAGES`, a map of page-name → render function (`dashboard`, `practice`, `history`, `analytics`, `achievements`, `plan`, `results`, `settings`). Each function reads from `window.PREP`, builds HTML strings, and injects them into the current page's DOM. No templating engine — just string concatenation with a local `esc()` helper for untrusted text.
- **`js/app.js`** — the app shell. On `DOMContentLoaded` it: applies saved display settings, builds and injects the sidebar `<nav>` (the `NAV` array is the single list of screens/labels/icons), wires the mobile menu, hydrates inline icons, then looks up `body[data-page]` and invokes the matching function from `window.PREP_PAGES`.
- **`js/chart.js`** — `window.createChart(container, options)`: a dependency-free inline-SVG line chart with trend line, markers, and tooltips. Returns `{ update(partial) }` so pages can redraw on filter changes (see `pages.analytics`).
- **`js/icons.js`** — `window.icon(name, size)` returns inline SVG markup; `window.hydrateIcons(root)` fills any `[data-icon]` element.
- **`css/styles.css`** — the entire design system (colors, type, components, responsive rules) in one file. No CSS preprocessor.

### Page wiring convention

Each HTML file's `<body>` carries two data attributes that drive `app.js`:
- `data-page="<name>"` — selects which function in `window.PREP_PAGES` to run.
- `data-nav="<file>.html"` — marks the matching sidebar link `aria-current="page"`.

When adding a new screen: create the HTML file with these attributes and the five `<script>` tags, add an entry to the `NAV` array in `js/app.js`, and add a render function to `js/pages.js` under the matching key.

### Data model notes

- An attempt's `status` is one of `completed | incomplete | missed`. Only `completed` attempts have a `score`; incomplete/missed attempts are never scored (by design, not a bug).
- `P.ref` (in `data.js`) is the latest attempt's date, and all "last N days" range filters (history, analytics) count backwards from it rather than from `Date.now()` — the prototype's dataset is meant to look current relative to itself.
- Settings (`settings.html`) persist to `localStorage` under `prepai.settings`; `window.PREP_SETTINGS()` reads them and `window.applyDisplaySettings()` applies text-size/reduce-motion globally. There is no server-side persistence anywhere.

### Known prototype limitations (see README.md)

- The microphone/waveform UI in `practice.html` is visual only — no real recording. Hook up `MediaRecorder`/speech-to-text inside `setRecording()` in `pages.js`.
- Finishing a practice interview always redirects to the latest existing sample result rather than creating a new scored entry.
