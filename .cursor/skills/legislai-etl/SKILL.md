---
name: legislai-etl
description: Ingest and normalize congressional data for LegislAI via Congress.gov API, RSS monitoring, bill processors, and backfill. Use when working on services/congress_*, rss_*, *bill_processor*, backfill, or ingestion bugs.
---

# LegislAI ETL

## Scope

`services/congress_api.py`, `services/congress_rss.py`, `services/rss_monitoring.py`, `services/bill_processor.py`, `services/bill_sync.py`, `services/backfill_orchestrator.py`, related scripts under `scripts/monitoring/` and Congress debug scripts.

## Responsibilities

1. Fetch bill metadata, text, and actions from Congress sources.
2. Normalize into shapes Bill / BillAction already accept — **persist `Bill.full_text` + `content_hash` + `full_text_fetched_at` on ingest**.
3. Respect rate limits and backoff (`docs/BACKOFF_IMPLEMENTATION.md`, `docs/LIMIT_ENFORCEMENT_SUMMARY.md`). Use `get_shared_congress_api()` so spacing is process-wide.
4. Support both live RSS and backfill batch size discipline (often batch size 1).
5. **Do not run Gemini inside `process_bill_data`.** Ingest only; callers (`routes._perform_analysis_async`, workflow/backfill) queue analysis off the HTTP thread. Keep `local_minute_budget` waits in background analysis only.

## Rules

- **Do not** edit `templates/` or invent DB columns in this skill’s turn.
- Need a new column? Stop → handoff to Database with field name, type, nullability, sample payload.
- **Do not** set `display_ready=True`; Analysis owns readiness after artifacts exist.
- Prefer existing processors over new parallel ingest paths.
- Prefer stored `bill.full_text` / payload text for hashing — never re-fetch Congress text in the same ingest when text is already present.
- Secrets: never open `.env`; `CongressAPI` should use configured env already loaded by the app.

## Downstream handoff triggers

| Change | Notify |
|--------|--------|
| New bill metadata field | Database, then API/Frontend if shown |
| New action type / status string length | Database (column length), Frontend formatting |
| Text fetch / persist shape change | Analysis (chunking / full text) + API |
| RSS item identity change | Database uniqueness / dedupe logic |

## References

- `docs/WORKFLOW_README.md`
- `docs/DATABASE_POPULATION_GUIDE.md`
- `docs/PRODUCTION_BACKFILL_GUIDE.md`
- `.cursor/resources/pipeline-contract.md`
- `services/congress_api.py` (`get_shared_congress_api`)
