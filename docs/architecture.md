# Sakura Study OS Architecture Notes

This project is intentionally local-first and lightweight, but new features should not keep growing the two largest files forever.

## Current Boundaries

- `app.py`
  - HTTP routes and legacy orchestration.
  - Database migrations and query helpers.
  - AI coach, question import, daily practice, reminders, textbooks and exports.
- `sakura_config.py`
  - Local `.env` loading and in-place secret/config updates.
- `sakura_ai.py`
  - OpenAI-compatible chat client and JSON response extraction.
  - AI teacher protocol, intent routing, strategy selection and memory compression.
- `sakura_profile.py`
  - Learner-profile statistics, local profile synthesis and optional AI profile polishing.
  - Pure study-phase, capacity-estimation and local-plan narrative calculations.
- `sakura_coach.py`
  - AI-coach settings state, review backlog, weak-point ranking, daily action planning and optional AI narrative.
- `sakura_export.py`
  - Printable mistake-PDF rendering, cover generation, image compression and CJK title rasterization.
- `sakura_backup.py`
  - Migration ZIP export/restore filesystem operations and archive safety checks.
- `sakura_reflection.py`
  - Weekly/monthly reflection statistics, local narrative, AI prompt assembly and persistence.
- `sakura_daily.py`
  - Daily-practice rules, due-review grouping, practice batches and quick feedback updates.
- `sakura_textbook.py`
  - Textbook PDF import, page-image rendering orchestration and paragraph indexing.
  - Textbook page context assembly and AI explanation prompt construction.
- `sakura_filters.py`
  - Question/document filter SQL assembly and scoped dropdown option queries.
- `sakura_retention.py`
  - Review interval constants, wrong-status detection and meta-tag normalization.
- `sakura_models.py`
  - Question/document JSON shaping, document-kind normalization and meta-tag statistics.
- `sakura_auth.py`
  - Password-gated login page rendering and signed browser session tokens.
- `sakura_db.py`
  - Data directory setup, SQLite connection creation, schema bootstrap and additive migrations.
- `sakura_classify.py`
  - Local keyword classification, chapter cleanup, duplicate chapter normalization and PDF-page chapter extraction.
- `sakura_insights.py`
  - Wrong-question insight fallback, AI insight normalization, analysis prompt assembly and insight persistence.
- `sakura_hints.py`
  - Scaffolding hints, full-solution prompt assembly and progressive variant generation.
- `sakura_teacher_memory.py`
  - AI teacher memory CRUD, mentor-experience parsing and relevance ranking.
- `sakura_reminders.py`
  - Reminder settings normalization.
  - Sakura-managed crontab block generation and installation.
- `sakura_pdf.py`
  - PDF page rendering.
  - Simulated-exam question-number slicing.
  - Cross-page question continuation stitching.
- `sakura_notifications.py`
  - PushPlus and WeCom robot HTTP senders.
  - Notification channel fan-out and normalized send result.
  - Daily, weather, morning and night-check reminder payload builders.
- `sakura_weather.py`
  - Weather location normalization and geocoding.
  - Tomorrow forecast retrieval with Open-Meteo and wttr.in fallback.
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

- `app.py`: AI-teacher context assembly and recent-evidence query can move into a service module.
- `static/reminders.js`: reminder-specific UI state and bindings.

Do these incrementally. Each split should include syntax checks and a server smoke test.
