# PrepAI – minimal interview practice dashboard

Plain HTML, CSS and JavaScript. No build step, no frameworks, no CDN scripts.
Open `index.html` in a browser. (Only the Inter font loads from Google Fonts; the app falls back to system fonts offline.)

## Screens
| File | Screen |
|---|---|
| index.html | Dashboard |
| practice.html | Practice Interview (add `?focus=structure` etc. for a skill drill) |
| history.html | Interview History |
| analytics.html | Progress Analytics |
| achievements.html | Achievements |
| plan.html | Improvement Plan |
| results.html | Detailed Interview Results (`?id=a8`) |
| settings.html | Settings (saved in the browser's localStorage) |

## Files
- `css/styles.css` – the single design system (colours, type, components, responsive rules)
- `js/data.js` – sample data. Replace with real assessment data; every figure on screen is calculated from it
- `js/chart.js` – dependency-free SVG line chart with tooltips
- `js/pages.js` – logic for each screen
- `js/app.js` – sidebar, mobile menu, display settings
- `js/icons.js` – inline SVG line icons

## Prototype notes
- The microphone button and waveform are visual only. Connect `MediaRecorder` / speech-to-text in `pages.js` (`setRecording`).
- Finishing a practice interview opens the latest sample result rather than saving a new one.
- Missed and incomplete interviews never receive a score.
