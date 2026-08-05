# Fix analysis pipeline — handoffs

Date: 2026-08-04
Status: complete

## Handoff: Analysis → Gemini Ops + API

Status: ready

### Change
- Size-aware tiers: A (full-text two-pass), B (map-reduce + resume), C (minimal)
- `analysis_data` keys: `analyzed_chunk_keys`, `chars_analyzed`, `total_chars`, `analysis_tier`, character `completion_percentage`
- `analysis_method`: `single_pass_full_text` | `map_reduce_macro_chunks` | `minimal`
- Governor: RPM + TPM; all Gemini calls via `_call_ai_model`
- Chunker: non-overlapping sections; macro packing for Tier B

### Contract delta
- Fields added: see pipeline-contract Analysis tier section
- Migration required: no
- display_ready impact: none on successful Tier A; partials when artifacts exist

### Next owner actions
- [x] Gemini Ops: preserve continuation/partial alerts; support `in_flight` extra (already passthrough)
- [x] API: `allow_budget_waits=False`, in-flight lock, delayed Tier B waves
- [x] Frontend: honest copy + light poll
- [x] QA: `test/test_size_aware_analysis.py` + updated `test_analysis_continuation_ops.py`

## Handoff: API → Frontend

Status: ready

### Change
- `partial_analysis_warning` may include `chars_analyzed`, `total_chars`, `limit_cause`, `continuation_queued`
- Resume only for Tier B partials
- Honest free-tier copy when queued

## Handoff: Frontend → QA

Status: ready

### QA results
- Tier A routing + 100% completion: pass
- Tier B resume monotonic coverage: pass
- In-flight dedupe: pass
- Chunker no overlaps / no front-of-bill bias: pass
- Continuation ops (`allow_budget_waits=False`): pass
