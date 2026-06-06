# Sakura Study OS Architecture Notes

This project is intentionally local-first and lightweight, but new features should not keep growing the two largest files forever.

## Current Boundaries

- `app.py`
  - HTTP routes and legacy orchestration.
  - Database migrations and query helpers.
  - AI coach, question import, daily practice, reminders, textbooks and exports.
- `sakura_reminders.py`
  - Reminder settings normalization.
  - Sakura-managed crontab block generation and installation.
- `notify_daily.py`
  - CLI entry point for scheduled reminder jobs.
- `static/index.html`
  - Stable DOM shell and ID-bound controls.
- `static/app.js`
  - Browser state, API calls, rendering and event binding.
- `static/styles.css`
  - Shared visual system and component styles.

## Refactor Rules

- Keep `id` and `data-view` compatibility unless the JavaScript binding changes in the same patch.
- Move pure backend helpers out of `app.py` when they do not need request state.
- Prefer small service modules over another large class.
- Keep modules dependency-light:
  - Service modules may import standard library and receive paths/settings as parameters.
  - Avoid importing `DemoHandler` or web response helpers from service modules.
- Frontend feature sections should expose a small set of functions:
  - load
  - render
  - save/update
  - bind
- Avoid adding new global event listeners when a scoped helper such as `on()` or event delegation can handle it.

## Next Good Splits

- `sakura_pdf.py`: PDF rendering, question slicing, cross-page question stitching.
- `sakura_weather.py`: geocoding and weather reminder generation.
- `sakura_notifications.py`: PushPlus and WeCom sending.
- `sakura_ai.py`: LLM settings, prompts and response parsing.
- `static/reminders.js`: reminder-specific UI state and bindings.

Do these incrementally. Each split should include syntax checks and a server smoke test.
