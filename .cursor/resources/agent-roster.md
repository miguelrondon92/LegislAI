# LegislAI Agent Roster

## Roles

### Orchestrator (parent / coordinator)
- Owns cross-cutting features and sequencing.
- Does not implement deep domain logic when a specialist exists.
- Ensures ETL → Database → Analysis → API → Frontend → QA handoffs complete.
- Resolves contract conflicts using [pipeline-contract.md](pipeline-contract.md).

### ETL Agent
- Owns discovery and fetch of congressional data.
- Files: `services/congress_api.py`, `services/congress_rss.py`, `services/rss_monitoring.py`, `services/rss_debugger.py`, `services/bill_processor.py`, `services/enhanced_bill_processor.py`, `services/workflow_bill_processor.py`, `services/backfill_orchestrator.py`, `services/backend_feed.py`, related `scripts/monitoring/`, `scripts/debug/debug_congress_api.py`.
- Must not invent DB columns; propose fields via handoff to Database.
- Must not change templates; emit handoff for Frontend when new bill fields appear in UI.

### Database Agent
- Owns SQLAlchemy models, Alembic migrations, and Bill helper methods (`get_active_*`, `create_new_*_version`, `update_display_ready_status`).
- Files: `db_models.py`, `migrations/`, `manage.py`, `scripts/setup/`, `scripts/cleanup/` (data integrity only).
- Never stores secrets in models or migrations.
- When columns/JSON shapes change, publish schema delta in handoff for Analysis + API + Frontend.

### Analysis Agent
- Owns AI analysis pipeline and storage of analysis artifacts.
- Files: `services/enhanced_ai_analyzer.py`, `services/analysis_cache.py`, `services/analysis_session_scheduler.py`, `utils/bill_chunker.py`, `utils/text_processing.py`, `utils/constants.py` (policy categories).
- Reads schema surface; does not invent tables without Database.
- Output must satisfy [display-ready-contract.md](display-ready-contract.md).

### API / Routes Agent
- Owns HTTP surface and glue between services and templates.
- Files: `routes.py`, `auth.py`, `app.py`, `workflow_admin.py`, `utils.py` (route helpers), `services/workflow_orchestrator.py` (API-facing workflow status only when coordinating with ETL/Analysis).
- Keeps search / bill detail / profile / alerts / workflow endpoints consistent with model methods.
- Never hardcodes API keys; use env vars already loaded by the app.

### Frontend Agent
- Owns presentation and client behavior.
- Files: `templates/**`, `static/css/**`, `static/js/**`.
- Consumes Bill model methods and route context vars; never calls Congress/Gemini APIs directly.
- When `display_ready` or analysis JSON keys change, update templates/JS and note QA cases.

### QA Agent
- Owns verification of the full chain.
- Files: `test/**`, root `test_*.py`, `verify_*.py` (read-only diagnostics ok).
- Asserts: ingest stores Bill, analysis writes AIAnalysis/Summary/categories, `display_ready` flips, homepage/bill detail render.
- Never runs commands that print `.env` or secret values.

## Collaboration rules

1. Specialists stay in their path globs unless Orchestrator assigns an exception.
2. Cross-layer work uses `legislai-pipeline-handoff` after each completed layer.
3. Downstream agents treat handoff notes as requirements, not suggestions.
4. If ingestion adds a field the DB cannot store, **stop and hand off to Database first** — do not silently drop data.
5. If analysis JSON keys change, API and Frontend must update before the feature is “done”.

## Recommended extra agents (when needed)

- **Notifications**: `services/notification_*.py` — alerts/email after `display_ready`.
- **Ops/Scripts**: one-off `scripts/` maintenance — prefer QA + Database review for destructive scripts.
