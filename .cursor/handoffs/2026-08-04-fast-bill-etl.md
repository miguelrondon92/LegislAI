# Handoff: Fast bill ETL (persist text, async AI)

**Date:** 2026-08-04  
**From:** ETL / Database / API / Analysis  
**To:** Analysis, API, Frontend, QA, Gemini Ops

## What changed

- `Bill.full_text`, `full_text_fetched_at`, `content_hash` persisted on ingest; migration `d4e5f6a7b8c9` applied.
- `get_full_text()` returns stored text; fetches via `get_shared_congress_api()` and persists on miss.
- `process_bill_data` no longer calls `analyze_bill` (HTTP/ETL path stays Gemini-free).
- Search miss + bill_analysis cold path queue `_perform_analysis_async`.
- Analyzer prefers `bill.full_text`; `allow_budget_waits` keeps local_minute_budget waits for background jobs.

## Downstream needs

| Owner | Action |
|-------|--------|
| Analysis | Always prefer stored text; do not reintroduce sync Gemini in processors |
| API | Keep load paths async-only for AI |
| Frontend | Queued analysis shows via `partial_analysis_warning` / refresh messaging |
| QA | `test/test_fast_bill_etl.py` |
| Gemini Ops | `local_minute_budget` remains background governor vs `gemini_api_429` |

## Out of scope

- Chunk-index resume; raising free-tier RPM above 15.
