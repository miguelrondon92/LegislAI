# Handoff: bill work lease + shared Gemini rate budget

**Date:** 2026-08-05  
**Layers:** Database → Analysis → ETL → API → QA

## What changed

Cross-ingestor coordination so search, RSS workflow, and backfill do not double-analyze the same bill or each burn a full free-tier RPM window.

1. **`BillWorkLease`** + migration `e5f6a7b8c9d0` — unique `(bill_id, work_kind)` with TTL/holder (`analyze` | `enrich`).
2. **`services/bill_work_lease.py`** — `try_acquire` / `heartbeat` / `release` / `is_held` / `acquire` context manager.
3. **`GeminiRateBudget`** + `gemini_rate_budget_state` — process-wide FIFO admit; DB row for cross-process RPM/TPM ceiling.
4. **`get_shared_ai_analyzer()`** — routes, workflow, backfill share one analyzer/budget.
5. Call sites wired: routes slots → lease; workflow/backfill acquire before `analyze_bill`.

## Downstream impact

- **Analysis:** `_call_ai_model` admits via shared budget (no per-instance counters).
- **API:** `_try_acquire_analysis_slot` / enrichment slots are DB leases; in-flight UX unchanged.
- **ETL:** lease miss → workflow skip (`lease_held`); backfill → `lease_deferred`.
- **Frontend:** none (same async “analyzing” behavior).

## Verify

```bash
PYTHONPATH=. .venv/bin/python -m unittest \
  test.test_bill_work_lease test.test_gemini_rate_budget \
  test.test_workflow_rss_pipeline test.test_backfill_pipeline \
  test.test_size_aware_analysis.TestInFlightDedupe -v
flask db upgrade   # apply e5f6a7b8c9d0
```

## Out of scope

Congress request mutex; `BillAction` unique constraint; Redis / multi-host beyond shared DB.
