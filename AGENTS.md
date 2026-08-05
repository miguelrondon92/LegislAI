# LegislAI Agentic Development System

Multi-agent architecture for developing LegislAI end-to-end: ingestion → storage → AI analysis → API → UI.

Full details live under [`.cursor/`](.cursor/). Start with [`.cursor/resources/agent-roster.md`](.cursor/resources/agent-roster.md) and [`.cursor/resources/pipeline-contract.md`](.cursor/resources/pipeline-contract.md).

## Non-negotiable: secrets

**No agent may read private keys, API keys, passwords, or secret-bearing files — ever.**

Blocked paths include `.env`, `*.pem`, `*.key`, credential JSON, and production env files. Use `.env.example` and `config/*.template` only. Hooks enforce this; agents must also refuse if asked.

## Pipeline (source of truth)

```
RSS / Congress API  →  Bill (+ BillAction)
        ↓
EnhancedAIAnalyzer (Tier A full-text | Tier B map-reduce)
        → AIAnalysis + Summary + BillCategoryMapping + HiddenProvision
        ↓
display_ready=True  →  routes / templates / alerts / notifications
        ↓
analysis_enrichers (async, RPM-gated) → stakeholders + deep policy_analysis
```

Core analysis owns summary + category labels (`policy_areas` / `policy_implications.categories`) and **sneaky riders** (`hidden_provisions` → `HiddenProvision` table; UI reads the table only). **Stakeholder Analysis** and deep **Policy Analysis** are separate async Gemini enrichers (`services/analysis_enrichers.py`); they must not block `display_ready`. Bill detail UI: **Policy Areas** (badges) ≠ **Policy Analysis** (narrative) ≠ **N sneaky riders detected** (collapsible, DB-backed).

Any upstream schema or payload change **must** propagate through this chain via the handoff protocol. Contract: [`.cursor/resources/pipeline-contract.md`](.cursor/resources/pipeline-contract.md).

## Gemini contingency

When Gemini analysis fails (missing key, model error, quota, partial, empty result):

1. **Users** — keep existing UI warnings (`partial_analysis_warning` on bill analysis, enrichment pending placeholders, search/API-limit messages). Do not invent analysis; leave `display_ready=False` unless real artifacts exist.
2. **Logs** — emit structured lines via logger `legislai.ops.gemini` (`GEMINI_FAILURE class=... bill=...`) and **persist** `OpsAlert` rows for the in-app **Ops logs** UI (`/ops/logs`, unread card on the dashboard). Ops alerts include `provider_model` (from `utils.constants.GEMINI_MODEL`, e.g. `gemini-3.5-flash-lite`) and, for partials/enrichment deferrals, `limit_cause` (`local_minute_budget` vs `gemini_api_429`) plus progress in the message/extra.
3. **Resume** — partial analyses under 100% completion for **Tier B** (`map_reduce_macro_chunks`) resume from **bill detail** (`/bill/...`) as well as search when quota allows (async continuation with `force_continue`, `allow_budget_waits=False`). **429s are expected on free tier** — failed maps must **not** count as analyzed (`map_failed` / empty ≠ done); remapped via delayed waves. Fake-complete rows (all maps failed but stored as 100%) also resume via `_tier_b_needs_resume`. Never reduce empty stubs into a “mapping errors” complete summary. Tier A bills (`single_pass_full_text`) complete in one wave and do not re-queue. Analyzer may wait up to 1–2 local minute resets only when `allow_budget_waits=True` (offline/backfill). Lifecycle must appear in Ops logs: `continuation_queued` (info) when a wave is actually spawned, then `continuation_finished` (info / warning if still partial / error on exception). Do **not** persist OpsAlerts for in-flight skip / page-refresh while a wave is already running (logger only).
4. **Enrichments** — after core completes, routes queue `run_downstream_enrichments` under a separate in-flight lock. Ops: `enrichment_queued` / `enrichment_finished`. Quota checks must use `enrichment_quota_ok()` → `get_rate_limit_status()["remaining_requests"]` (or `get_quota_info()["current_usage"]`). **Never** read `get_quota_info()["status"]["safe_remaining_requests"]` — that key is not under `status` and falsely reports 0. On real RPM deferral: keep enrichments `pending`, do not churn analysis versions, cooldown until minute reset.
5. **Programmer** — primary surface is dashboard / `/ops/logs` (unread + bill filters). Optional email: set `OPS_ALERT_WEBHOOK_URL` (Zapier/Make/n8n). Independent of `NOTIFICATIONS_ENABLED`. Webhook deduped per `(failure_class, bill)` for `OPS_ALERT_COOLDOWN_SECONDS` (default 1800). After code changes that affect analysis/routes, **restart Flask and verify** `/bill/...` and `/ops/logs` yourself before instructing the user.
6. **Free tier** — Google AI Studio typically ~15–30 RPM and ~1,500 RPD (daily reset midnight Pacific). Local limiter uses 15 RPM. Over limit → API 429 `RESOURCE_EXHAUSTED`. Free-tier prompts may be used to improve Google products.
7. **Model provenance** — `GEMINI_MODEL` can change over time; every `AIAnalysis` / `Summary` / `HiddenProvision` write stamps `provider_model` at write time so history survives constant changes. Analysis agents must read the current `GEMINI_MODEL` before analysis work.

## Agent roster

| Agent | Focus | Primary paths |
|-------|--------|----------------|
| **Orchestrator** | Cross-cutting features, handoffs, conflict resolution | whole repo (coordination only) |
| **ETL** | Ingestion, Congress API, RSS, bill processors, backfill | `services/congress_*`, `services/rss_*`, `services/*bill_processor*`, `services/backfill_*` |
| **Database** | Models, migrations, indexes, versioning | `db_models.py`, `migrations/`, `manage.py` |
| **Analysis** | Gemini analysis, chunking, categories, enrichers, hidden provisions | `services/enhanced_ai_analyzer.py`, `services/analysis_enrichers.py`, `services/analysis_*`, `utils/bill_chunker.py`, `utils/text_processing.py` |
| **Gemini Ops** | `GEMINI_MODEL`, OpsAlert lifecycle, quota probes, `/ops/logs` | `services/ops_alert_service.py`, `utils/constants.py` (`GEMINI_MODEL`), `templates/ops_logs.html`, `scripts/debug/check_gemini_quota.py` |
| **API / Routes** | Flask routes, auth, workflow admin APIs | `routes.py`, `auth.py`, `app.py`, `workflow_admin.py` |
| **Frontend** | Jinja templates, CSS, JS, display-ready UX | `templates/`, `static/` |
| **QA** | Tests, fixtures, regression for pipeline | `test/`, root `test_*.py` |

## How to run work

1. Load skill `legislai-orchestrate` for multi-layer changes.
2. Spawn specialized subagents (or sequential turns) per layer touched.
3. After each layer finishes, run skill `legislai-pipeline-handoff` and notify the next owner.
4. QA validates `display_ready` and UI surface before closing.

## Skills

| Skill | When |
|-------|------|
| `legislai-orchestrate` | Feature spans 2+ layers |
| `legislai-etl` | Ingestion / Congress / RSS / backfill |
| `legislai-database` | Schema / migrations / model methods |
| `legislai-analysis` | AI analyzer / categories / hidden provisions |
| `legislai-gemini-ops` | `GEMINI_MODEL`, OpsAlert lifecycle, quota probes, `/ops/logs` |
| `legislai-frontend` | Templates / static / progressive loading |
| `legislai-pipeline-handoff` | After any layer change that affects downstream |
| `legislai-qa` | Verification and regression |

## Docs map

- Architecture: `docs/CLAUDE.md`
- Structure: `PROJECT_STRUCTURE.md`
- Workflow: `docs/WORKFLOW_README.md`
- Bill search: `docs/BILL_SEARCH_WORKFLOW_GUIDE.md`
- DB: `docs/DATABASE_OPTIMIZATION_SUMMARY.md`, `docs/DATABASE_POPULATION_GUIDE.md`
- Analysis pipeline: `docs/ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md`
