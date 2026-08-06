# Handoff: RSS + Backfill admin UIs

**Date:** 2026-08-05  
**Layers:** API → Frontend → ETL → Gemini Ops → QA

## What changed

1. **RSS rename** — nav/titles say RSS; `/rss` + legacy `/workflow`; `/api/workflow/*` unchanged.
2. **Backfill dashboard** — `/backfill` + `/api/backfill/start|stop|status|logs` via [`services/backfill_web.py`](../../services/backfill_web.py).
3. **Pause works** — `_process_bills_batch` honors `PAUSED`; `lease_deferred` is not a failure.
4. **Activity logs** — [`pipeline_activity_log.py`](../../services/pipeline_activity_log.py) ring buffers; panels on both dashboards.
5. **Ops Logs** — analyzer step emits `OpsAlert` with `source=rss` / `source=backfill` (no spam on lease skip).

## Verify

```bash
PYTHONPATH=. .venv/bin/python -m unittest discover -s test -p 'test_rss_backfill_ui.py' -v
# restart Flask, admin session:
# open /rss and /backfill; confirm 403 when not admin
```

## Downstream

- Ops UI already shows `source` — filter by `rss` / `backfill` in failure_class or scan source column.
- Shared lease/budget still applies when both UIs run.
