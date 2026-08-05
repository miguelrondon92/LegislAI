## Handoff: Analysis / API → QA / Frontend

- **Change:** Tier B recovery contract — failed maps (`map_failed` / empty) no longer count as analyzed; waves early-stop on Gemini 429; orphan/`map_failed` keys remapped on resume; refuse reduce / 100% when usable findings are incomplete or reduce narrates mapping failures. Routes resume fake-complete rows via `_tier_b_needs_resume` (bill detail, search, delayed waves).
- **Contract fields added/changed/removed:**
  - `limit_cause` may be `map_failures` (in addition to `local_minute_budget` | `gemini_api_429`)
  - Usable-only `analyzed_chunk_keys` / `tier_b_map_findings` (failed ≠ done)
  - Documented in `.cursor/resources/pipeline-contract.md` (Tier B 429 recovery) and `AGENTS.md` Resume
- **Migration needed:** no
- **display_ready impact:** Do not ship complete / garbage “mapping errors” summaries. Complete only after usable maps cover all macros and a real reduce.
- **Downstream owners:** Analysis | API | QA | Frontend (partial banner / resume UX)
- **Suggested tests:** `test/test_size_aware_analysis.py` — failed ≠ done, remap `map_failed`, refuse false 100%, `_tier_b_needs_resume` fake-complete
- **Verified:** 119-HR8800 remapped 0→6 usable macros; Bill Summary is substantive NDAA FY2027 text; `is_partial=False`, `map_failed=0`; Ops `continuation_queued` → partial `continuation_finished` waves → final complete `continuation_finished`
