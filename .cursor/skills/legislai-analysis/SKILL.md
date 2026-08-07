---
name: legislai-analysis
description: Implement and maintain LegislAI Gemini-based bill analysis, category mapping, summaries, downstream enrichers, and hidden provisions. Use when working on enhanced_ai_analyzer, analysis_enrichers, analysis sessions/cache, bill chunking, or analysis JSON shape.
---

# LegislAI Analysis

## Scope

`services/enhanced_ai_analyzer.py`, `services/analysis_enrichers.py`, `services/analysis_*.py`, `utils/bill_chunker.py`, `utils/text_processing.py`, `utils/constants.py` (categories).

## Responsibilities

1. Produce versioned `AIAnalysis` + `Summary` rows.
2. Store `BillCategoryMapping` (and sneakiness when applicable).
3. Detect/store `HiddenProvision` when in scope.
4. Invoke `Bill.update_display_ready_status()` after successful **core** writes (not blocked on enrichments).
5. Keep JSON keys compatible with route category extraction and templates.
6. **Model context** — before any analysis work, read `utils.constants.GEMINI_MODEL` and `EnhancedAIAnalyzer.model_name`. Do not assume a hardcoded model string.
7. **Stamp `provider_model`** on every `AIAnalysis` / `Summary` / `HiddenProvision` write (column + `analysis_data.provider_model`). When `GEMINI_MODEL` changes later, existing rows keep their stamped model.
8. **Size-aware routing** — Tier A `single_pass_full_text` (≤~150k tokens, ~2 Gemini calls: core + integrity); Tier B `map_reduce_macro_chunks` with `analyzed_chunk_keys` resume. UI waves use `allow_budget_waits=False`.
9. **Downstream enrichers** — after core, attach `pending` stubs via `pending_enrichment_stubs()` + `attach_policy_areas()`. `run_downstream_enrichments` fills template-shaped `stakeholders` and deep `policy_analysis` when RPM allows. Gate with `enrichment_quota_ok()` (`get_rate_limit_status()["remaining_requests"]` ≥ 2). Never read `get_quota_info()["status"]["safe_remaining_requests"]`.

## Category formats (all must remain readable)

Support writers/readers for:

- `policy_areas.primary_category` / `secondary_categories` (UI badges)
- `policy_implications.categories[]` (mappings / display_ready)
- `policy_implications.category_breakdown{}` (legacy readers)
- `primary_category` / `secondary_categories` under `policy_implications`

See `.cursor/resources/pipeline-contract.md`.

## Rules

- Do not call template files; hand off UI needs.
- Schema changes require Database skill/agent first.
- Never log API key values; never read `.env`.
- Tolerate missing full text (fallback to summary) as existing code does.
- On Gemini failure: do not invent analysis; keep `display_ready` false unless real artifacts exist; ensure `notify_gemini_failure` persists an `OpsAlert` and logs via `legislai.ops.gemini` (`services/ops_alert_service.py`). Webhook email is optional.
- Coordinate `GEMINI_MODEL` changes with Gemini Ops; Analysis owns stamping onto rows.
- Enrichment deferral: leave status `pending`, do not churn AIAnalysis versions for false skips.

## Handoff

| Change | Notify |
|--------|--------|
| New JSON key | API + Frontend + QA |
| New DB field for scores | Database first, then API/Frontend |
| display_ready inputs change | Database + API + Frontend + QA |
| Model stamp / `provider_model` column | Database + Gemini Ops + QA |
| Enricher shape / ops classes | Gemini Ops + API + Frontend + QA |

## References

- `.cursor/resources/pipeline-contract.md`
- `.cursor/handoffs/2026-08-04-downstream-enrichers.md`
- `docs/ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md`
- `test/test_downstream_enrichers.py`, `test/test_size_aware_analysis.py`
- `utils/constants.py` (`GEMINI_MODEL`)
