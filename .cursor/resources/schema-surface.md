# Schema Surface (agent-facing)

Authoritative definitions live in `db_models.py`. This is a navigation aid for specialists.

## Core tables

| Model | Purpose | Key fields / notes |
|-------|---------|-------------------|
| `Bill` | Legislative bill | Natural key `congress,bill_type,bill_number`; `active`, `version`, `display_ready`; legacy JSON columns still exist — prefer related tables |
| `BillAction` | Timeline events | Ordered by `action_date` |
| `AIAnalysis` | Versioned AI results | `analysis_data` JSON text; `complexity_score`, `controversy_score`; `active`, `analysis_version` |
| `Summary` | Versioned summaries | `summary_text`, `plain_language_summary`, `key_provisions` JSON; `active` |
| `BillCategoryMapping` | Bill ↔ policy | Relevance + `sneakiness_score` |
| `HiddenProvision` | Risk findings | Linked to bill; sneakiness/risk metadata |
| `PolicyCategory` | 36 federal categories | Seed via `scripts/setup/create_policy_categories.py`; names in `utils/constants.py` |
| `User` / `UserPolicySubscription` | Auth + prefs | Interest levels, notification settings |
| `Alert` / `UserBillAlignment` | Personalization | Alignment scores |
| `WatchlistItem` | User tracking | Per-user bill list |
| `AnalysisSession` | Analysis session tracking | Used by analysis session scheduler |
| `OpsAlert` | Programmer Gemini/ops failures | `is_read`, bill filters; UI at `/ops/logs` |

## Preferred Bill accessors

Use these instead of raw legacy columns when possible:

- `get_active_ai_analysis()`, `get_ai_analysis_new()`
- `get_active_summary()`, `get_summary_text()`, `get_plain_language_summary()`
- `get_complexity_score_new()`, `get_controversy_score_new()`
- `create_new_analysis_version(...)`, `create_new_summary_version(...)`
- `update_display_ready_status()`

## Migrations

- Alembic under `migrations/versions/`
- After model changes: generate migration, review upgrade/downgrade, never put secrets in migration scripts
- Population: `docs/DATABASE_POPULATION_GUIDE.md`
