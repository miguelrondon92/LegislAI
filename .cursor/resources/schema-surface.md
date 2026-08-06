# Schema Surface (agent-facing)

Authoritative definitions live in `db_models.py`. This is a navigation aid for specialists.

## Core tables

| Model | Purpose | Key fields / notes |
|-------|---------|-------------------|
| `Bill` | Legislative bill | Natural key `congress,bill_type,bill_number`; `full_text` (persisted Congress text), `full_text_fetched_at`, `content_hash`; `synced_congress_update_date` (shared ETL freshness vs Congress `updateDate`); `backfill_last_visited_at` (catalog walk only); `active`, `version`, `display_ready`; legacy JSON columns still exist — prefer related tables |
| `BillAction` | Timeline events | Ordered by `action_date` |
| `AIAnalysis` | Versioned AI results | `analysis_data` JSON text; `complexity_score`, `controversy_score`; `provider_model` (Gemini at write time); `active`, `analysis_version`. Enrichment fields live **inside** JSON (`policy_areas`, `policy_analysis`, `stakeholders`) — no separate table |
| `Summary` | Versioned summaries | `summary_text`, `plain_language_summary`, `key_provisions` JSON; `provider_model`; `active` |
| `BillCategoryMapping` | Bill ↔ policy | Relevance + `sneakiness_score` |
| `HiddenProvision` | Hidden provisions (UI) | Canonical store for profile/search/home; risk metadata; `provider_model`. Filled from analysis JSON on complete analyze + heal |
| `PolicyCategory` | 36 federal categories | Seed via `scripts/setup/create_policy_categories.py`; names in `utils/constants.py` |
| `User` / `UserPolicySubscription` | Auth + prefs | Interest levels, notification settings |
| `Alert` / `UserBillAlignment` | Personalization | Alignment scores |
| `WatchlistItem` | User tracking | Per-user bill list |
| `AnalysisSession` | Analysis session tracking | Used by analysis session scheduler |
| `OpsAlert` | Programmer Gemini/ops failures | `is_read`, `provider_model`, bill filters; UI at `/ops/logs` |
| `BillWorkLease` | Cross-ingestor work mutex | Unique `(bill_id, work_kind)` for `analyze` / `enrich`; TTL + holder |
| `GeminiRateBudgetState` | Cross-process Gemini ceiling | Single row `id=1`: minute window RPM/TPM counters |
| `BackfillCatalogState` | Per-congress backfill cursor | `next_index` over `introducedDate+asc` catalog; `sort_key` |

## Preferred Bill accessors

Use these instead of raw legacy columns when possible:

- `get_active_ai_analysis()`, `get_ai_analysis_new()`
- `get_active_summary()`, `get_summary_text()`, `get_plain_language_summary()`
- `get_complexity_score_new()`, `get_controversy_score_new()` — complexity helper returns **0–1** (`complexity_assessment.complexity_score` is 0.0–1.0; only ÷100 if legacy value `>1`); templates display ×100
- `get_hidden_provisions()`, `get_hidden_provisions_count()` — UI source of truth for **hidden provisions** (not analysis JSON)
- `create_new_analysis_version(...)`, `create_new_summary_version(...)`
- `update_display_ready_status()`

## Analysis JSON enrichments (no migration)

Downstream stakeholder + policy narrative are stored on the active `AIAnalysis.analysis_data`:

- Written as `pending` stubs by core Tier A/B completion
- Filled by `services/analysis_enrichers.run_downstream_enrichments` when RPM allows
- Canonical shapes: see [pipeline-contract.md](pipeline-contract.md) (§ Policy areas vs enrichments)

## Migrations

- Alembic under `migrations/versions/`
- After model changes: generate migration, review upgrade/downgrade, never put secrets in migration scripts
- Population: `docs/DATABASE_POPULATION_GUIDE.md`
