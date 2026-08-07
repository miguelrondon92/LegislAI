# Handoff: ETL unification (bill_sync)

**Date:** 2026-08-05  
**From:** ETL / API  
**To:** Analysis, Frontend, QA, Gemini Ops

## What changed

- New shared entry: [`services/bill_sync.py`](../services/bill_sync.py) — `sync_bill`, `refresh_activity`, `resolve_active_bill`, `needs_activity_refresh`, `get_bills_without_analysis`.
- **Two freshness axes** (Bill version model unchanged):
  - Activity refresh: actions + status on active row; no Gemini; no version fork; no `display_ready` change.
  - Content ingest: still via `BillProcessor.process_bill_data` (may fork version on `content_hash` change).
- Search / bill detail: TTL-gated (6h) async activity refresh; cold miss uses `sync_bill`.
- RSS / workflow: uses `bill_sync`; passes **Bill object** to `analyze_bill`; uses `bill.get_full_text()`; bill-level queue dedupe; notifications only on real changes; all eight bill types parsed.
- Backfill: gap detection uses `get_active_ai_analysis()`; `get_shared_congress_api()`; ingest via `bill_sync`; `--prod` state file set before load.
- Removed: `services/workflow_bill_processor.py`, `routes.fetch_bill_actions_from_api`, duplicated category/hidden storage in workflow + backfill.

## Contract fields added/changed/removed

- Added pipeline-contract section: ETL entry points + two freshness axes.
- No DB schema / migration changes.

## Migration needed

No.

## display_ready impact

- Activity refresh does not touch `display_ready`.
- Content-hash version fork still creates a new row with `display_ready=False` and no carried analysis (known trade-off; out of scope).

## Downstream owners

| Owner | Action |
|-------|--------|
| Analysis | Keep persisting via `analyze_bill(bill)`; do not reintroduce Gemini in ETL |
| API | Prefer `bill_sync` for any new ingest paths |
| Frontend | Timeline may grow after async refresh — refresh/poll already covers this |
| QA | `test/test_bill_sync.py`; workflow + ETL suites |
| Gemini Ops | Workflow analysis now attributes OpsAlerts to real bills |

## Suggested tests

```bash
python -m unittest test.test_bill_sync test.test_fast_bill_etl -v
```

## Follow-ups (out of scope)

- Carry-forward analysis on content-hash version fork / single-row versioning.
- `AIAnalysis.based_on_content_hash` for explicit staleness.
- Action-triggered alerts (“bill passed”).
