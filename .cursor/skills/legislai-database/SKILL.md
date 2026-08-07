---
name: legislai-database
description: Design and evolve LegislAI SQLAlchemy models, Alembic migrations, and Bill helper methods. Use when editing db_models.py, migrations/, manage.py, or when ETL/analysis need new storage fields.
---

# LegislAI Database

## Scope

`db_models.py`, `migrations/`, `manage.py`, setup/cleanup scripts that touch schema or referential integrity.

## Responsibilities

1. Evolve schema with versioning for `AIAnalysis` and `Summary`.
2. Keep Bill accessors (`get_active_*`, `create_new_*_version`, `update_display_ready_status`) correct.
3. Ship Alembic migrations with every model change.
4. Update `.cursor/resources/schema-surface.md` when tables/fields change meaningfully.

## Rules

- Prefer normalized tables over stuffing new blobs into legacy `Bill.ai_analysis` unless temporary compatibility requires it.
- Migrations: no secrets, no irreversible data loss without explicit user approval.
- `display_ready` logic must match `.cursor/resources/display-ready-contract.md`.
- Policy categories: keep aligned with `utils/constants.py` seed data.

## Handoff

After migration + model update:

1. Analysis — how to write/read new fields
2. API — query/filter implications
3. Frontend — which accessors to use in templates
4. QA — migration + model tests

## References

- `docs/DATABASE_OPTIMIZATION_SUMMARY.md`
- `archives/docs/DATABASE_OPTIMIZATION_IMPLEMENTATION_LOG.md`
- `.cursor/resources/schema-surface.md`
