---
name: legislai-etl
description: Ingest and normalize congressional data for LegislAI via Congress.gov API, RSS monitoring, bill processors, and backfill. Use when working on services/congress_*, rss_*, *bill_processor*, backfill, backend_feed, or ingestion bugs.
---

# LegislAI ETL

## Scope

`services/congress_api.py`, `services/congress_rss.py`, `services/rss_monitoring.py`, `services/bill_processor.py`, `services/enhanced_bill_processor.py`, `services/workflow_bill_processor.py`, `services/backfill_orchestrator.py`, `services/backend_feed.py`, related scripts under `scripts/monitoring/` and Congress debug scripts.

## Responsibilities

1. Fetch bill metadata, text, and actions from Congress sources.
2. Normalize into shapes Bill / BillAction already accept.
3. Respect rate limits and backoff (`docs/BACKOFF_IMPLEMENTATION.md`, `docs/LIMIT_ENFORCEMENT_SUMMARY.md`).
4. Support both live RSS and backfill batch size discipline (often batch size 1).

## Rules

- **Do not** edit `templates/` or invent DB columns in this skill’s turn.
- Need a new column? Stop → handoff to Database with field name, type, nullability, sample payload.
- **Do not** set `display_ready=True`; Analysis owns readiness after artifacts exist.
- Prefer existing processors over new parallel ingest paths.
- Secrets: never open `.env`; `CongressAPI` should use configured env already loaded by the app.

## Downstream handoff triggers

| Change | Notify |
|--------|--------|
| New bill metadata field | Database, then API/Frontend if shown |
| New action type / status string length | Database (column length), Frontend formatting |
| Text fetch shape change | Analysis (chunking / full text) |
| RSS item identity change | Database uniqueness / dedupe logic |

## References

- `docs/WORKFLOW_README.md`
- `docs/DATABASE_POPULATION_GUIDE.md`
- `docs/PRODUCTION_BACKFILL_GUIDE.md`
- `.cursor/resources/pipeline-contract.md`
