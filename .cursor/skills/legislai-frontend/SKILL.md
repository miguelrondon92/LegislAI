---
name: legislai-frontend
description: Build and fix LegislAI Jinja templates, CSS, and JS for dashboards, bill detail, search, and progressive loading. Use when editing templates/ or static/, or when display_ready and analysis fields must appear in the UI.
---

# LegislAI Frontend

## Scope

`templates/**`, `static/css/**`, `static/js/**`.

## Responsibilities

1. Render bill analysis, categories, scores, actions, alerts using route context and Bill helpers.
2. Handle incomplete analysis / progressive loading when not `display_ready`.
3. Keep admin/workflow dashboards usable without exposing secrets in HTML.
4. On `bill_analysis.html`:
   - **Policy Areas** — badges from `policy_areas` (fallback `policy_implications`)
   - **Policy Analysis** — deep fields from `policy_analysis` (pending/skipped placeholders via `enrichment_flags`)
   - **Stakeholder Analysis** — `affected_groups` / `winners_losers` (not legacy top-level `winners`/`losers`)
5. Light auto-poll (~18s, max N) when Tier B continuation or enrichment is queued.

## Rules

- Prefer `get_complexity_score_new()`, `get_active_summary()`, etc.
- No direct API keys in JS; no `fetch` to Gemini/Congress from the browser for analysis.
- Match existing Bootstrap/template patterns in `base.html`.
- If a value is missing, hand off upstream — do not fabricate analysis client-side.
- Pending enrichments ≠ blank cards: show honest queued copy.

## Handoff

- Context var missing → API/Routes (`enrichment_flags`, analysis dict)
- Column/accessor missing → Database
- Analysis key missing → Analysis
- Always ping QA for bill_detail / homepage / search regressions

## References

- `.cursor/resources/pipeline-contract.md` (Policy areas vs enrichments)
- `.cursor/resources/display-ready-contract.md`
- `archives/docs/PROGRESSIVE_LOADING_ENHANCEMENT.md`
- `archives/docs/FRONTEND_LEGISLATIVE_PROGRESS_FIX.md`
- `archives/docs/HOMEPAGE_SUMMARY_TABLE_FIX.md`
