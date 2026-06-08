# Sakura Study OS Architecture Notes

This project is intentionally local-first and lightweight, but new features should not keep growing the two largest files forever.

## Current Boundaries

- `app.py`
  - HTTP routes and legacy orchestration.
  - Database migrations and query helpers.
  - AI coach, question import, daily practice, reminders, textbooks and exports.
- `sakura_config.py`
  - Local `.env` loading and in-place secret/config updates.
- `sakura_settings.py`
  - Runtime settings payload shaping, secret masking and public URL validation.
- `sakura_ai.py`
  - OpenAI-compatible chat client and JSON response extraction.
  - AI teacher protocol, intent routing, strategy selection and memory compression.
- `sakura_profile.py`
  - Learner-profile statistics, local profile synthesis and optional AI profile polishing.
  - Pure study-phase, capacity-estimation and local-plan narrative calculations.
- `sakura_coach.py`
  - AI-coach settings state, review backlog, weak-point ranking, daily action planning and optional AI narrative.
  - AI-teacher context assembly and recent wrong/review evidence queries.
- `sakura_export.py`
  - Mistake-export filter SQL, selected-row loading and printable PDF rendering.
  - Cover generation, image compression and CJK title rasterization.
- `sakura_backup.py`
  - Migration ZIP export/restore filesystem operations and archive safety checks.
- `sakura_migration.py`
  - In-memory migration job status tracking and background restore-job orchestration.
- `sakura_reflection.py`
  - Weekly/monthly reflection statistics, local narrative, AI prompt assembly and persistence.
- `sakura_daily.py`
  - Daily-practice rules, due-review grouping, practice batches and quick feedback updates.
- `sakura_textbook.py`
  - Textbook PDF import, page-image rendering orchestration and paragraph indexing.
  - Textbook page context assembly and AI explanation prompt construction.
- `sakura_filters.py`
  - Question/document filter SQL assembly and scoped dropdown option queries.
- `sakura_documents.py`
  - Document listing, document metadata updates and question/document deletion cleanup.
  - Safe data-directory file deletion and empty-document pruning.
- `sakura_questions.py`
  - Question index/detail SQL queries and category/subject aggregate statistics.
- `sakura_retention.py`
  - Review interval constants, wrong-status detection and meta-tag normalization.
- `sakura_models.py`
  - Question/document JSON shaping, document-kind normalization and meta-tag statistics.
- `sakura_auth.py`
  - Password-gated login page rendering and signed browser session tokens.
- `sakura_http.py`
  - Minimal JSON, text and redirect response helpers for `BaseHTTPRequestHandler`.
- `sakura_parse.py`
  - Small request/form parsing helpers for integers, boolean flags and bounded values.
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
  - Browser state, shared API/render helpers, route/view switching and cross-feature event binding.
- `static/reminders.js`
  - Reminder/check-in/weather/notification settings UI helpers.
  - Loaded before `app.js`; functions execute after shared browser helpers are initialized.
- `static/dashboard.js`
  - Dashboard subject/document filters, overview metrics and distribution-stat rendering.
  - Loaded after `app.js`; exposes `SakuraDashboard.load()` for shared refresh.
- `static/question_detail.js`
  - Question detail modal, AI hint/analysis/variation actions, crop tool and image lightbox.
  - Loaded after `app.js`; exposes `openDetail()` and `openLightbox()` for shared card/list interactions.
- `static/documents.js`
  - Book/mock-paper document cards plus edit, delete and chapter-rescan actions.
  - Loaded after `app.js`; exposes `SakuraDocuments.render()` so shared refresh can update document grids.
- `static/library.js`
  - Library question loading, scoped filters, search, question cards, quick locate and question update/delete actions.
  - Loaded after `app.js` and before `mistakes.js`; exposes compatibility functions used by question detail, coach and export modules.
- `static/archives.js`
  - Profile archive and teacher-memory archive dialog helpers.
  - Loaded after `app.js` and before `coach.js`; exposes archive dialog functions used by the coach panel.
- `static/chapter_stats.js`
  - Chapter correct-rate cards and wrong-reason radar chart rendering.
  - Loaded after `app.js`; exposes `SakuraChapterStats.load()` for view navigation and document-card stats links.
- `static/upload.js`
  - Book and mock-paper PDF upload form bindings.
  - Loaded after `app.js`; refreshes shared document/question state after imports.
- `static/mistakes.js`
  - Mistake-page filters, focused wrong/review toggles, mistake grid and selection hint rendering.
  - Loaded after `app.js` and before `mistake_export.js`; exposes compatibility functions used by export controls.
- `static/ai_chat.js`
  - AI chat, LLM settings, teacher-memory and mentor-experience UI helpers.
  - Loaded after `app.js` so shared render/API helpers are initialized; exposes `loadAiChatPanel()` for view navigation.
- `static/reflection.js`
  - Reflection preview, AI-generated reflection output and history archive UI helpers.
  - Loaded after `app.js`; exposes `SakuraReflection.load()` for view navigation.
- `static/textbook.js`
  - Textbook upload, page navigation, paragraph selection, page-image lightbox and textbook AI chat UI helpers.
  - Loaded after `app.js`; exposes `SakuraTextbook.load()` for refresh and view navigation.
- `static/daily.js`
  - Daily practice rendering and custom practice-rule form/list UI helpers.
  - Loaded after `app.js`; exposes `SakuraDaily.load()` and `SakuraDaily.populateFilters()` for refresh and view navigation.
- `static/coach.js`
  - Learning-profile settings, profile refresh, plan generation and AI-coach plan rendering.
  - Loaded after `app.js`; exposes `SakuraCoach.load()` for view navigation.
- `static/mistake_export.js`
  - Mistake selection controls and filtered/selected PDF export UI helpers.
  - Loaded after `app.js`; exposes `SakuraMistakeExport.exportPdf()` for future export entry points.
- `static/backup.js`
  - Backup export/import and migration-panel bindings.
  - Loaded after `app.js` so shared helpers and refresh hooks are available.
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

## Validation

- Run `python tests\smoke_refactor.py` after backend refactors that touch PDF import, question updates, backup options or AI teacher persistence.
- Run Python `py_compile` and `node --check static\app.js` before each safety commit.

## Next Good Splits

- `app.py`: PDF import orchestration and route dispatch remain the largest backend areas.
- Continue splitting `static/app.js` by feature, using `static/reminders.js` as the first lightweight module pattern.

Do these incrementally. Each split should include syntax checks and a server smoke test.
