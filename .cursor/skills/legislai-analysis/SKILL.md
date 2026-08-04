---
name: legislai-analysis
description: Implement and maintain LegislAI Gemini-based bill analysis, category mapping, summaries, and hidden provisions. Use when working on enhanced_ai_analyzer, analysis sessions/cache, bill chunking, or analysis JSON shape.
---

# LegislAI Analysis

## Scope

`services/enhanced_ai_analyzer.py`, `services/analysis_*.py`, `utils/bill_chunker.py`, `utils/text_processing.py`, `utils/constants.py` (categories).

## Responsibilities

1. Produce versioned `AIAnalysis` + `Summary` rows.
2. Store `BillCategoryMapping` (and sneakiness when applicable).
3. Detect/store `HiddenProvision` when in scope.
4. Invoke `Bill.update_display_ready_status()` after successful writes.
5. Keep JSON keys compatible with route category extraction and templates.

## Category formats (all must remain readable)

Support writers/readers for:

- `policy_implications.categories[]`
- `policy_implications.category_breakdown{}`
- `primary_category` / `secondary_categories`

See `.cursor/resources/pipeline-contract.md`.

## Rules

- Do not call template files; hand off UI needs.
- Schema changes require Database skill/agent first.
- Never log API key values; never read `.env`.
- Tolerate missing full text (fallback to summary) as existing code does.

## Handoff

| Change | Notify |
|--------|--------|
| New JSON key | API + Frontend + QA |
| New DB field for scores | Database first, then API/Frontend |
| display_ready inputs change | Database + API + Frontend + QA |

## References

- `docs/ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md`
- `docs/AI_ANALYZER_CONSOLIDATION_LOG.md`
- `docs/HIDDEN_PROVISIONS_IMPLEMENTATION_SUMMARY.md`
- `docs/STANDARDIZED_ANALYSIS_IMPLEMENTATION.md`
