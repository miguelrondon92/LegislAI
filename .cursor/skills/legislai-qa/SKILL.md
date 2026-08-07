---
name: legislai-qa
description: Verify LegislAI pipeline regressions across ingest, storage, analysis, display_ready, and UI/API. Use when adding tests, validating a handoff, or confirming an end-to-end feature before close.
---

# LegislAI QA

## Scope

`test/`, root `test_*.py`, `verify_*.py` (prefer consolidating into `test/` over new root scripts).

## Minimum E2E checklist

- [ ] Bill upserted with natural key `(congress, bill_type, bill_number)`
- [ ] Actions stored when ETL provides them
- [ ] Active `AIAnalysis` + `Summary` created
- [ ] `BillCategoryMapping` present
- [ ] `display_ready` transitions to true when inputs complete
- [ ] `display_ready` does **not** require enrichments ready
- [ ] Enricher merge produces template-shaped `stakeholders` + `policy_analysis`
- [ ] `enrichment_quota_ok` / deferral does not false-skip when RPM remains
- [ ] Bill detail / search / homepage paths tolerate incomplete vs ready states
- [ ] No secret values in fixtures or assertion messages

## Practice

- Mock Congress/Gemini where possible (`docs` + existing test patterns).
- Prefer extending `test/test_downstream_enrichers.py`, `test/test_size_aware_analysis.py`, `test/test_workflow_integration.py`, bill search tests, homepage tests.
- After route/analyzer/template changes: restart Flask and curl `/bill/...` + `/ops/logs` before closing.
- Never `cat .env` or print `os.environ` secret keys in test output.

## On failure

Open a handoff back to the owning layer (ETL/DB/Analysis/API/Frontend) with failing assertion and expected contract cite.
