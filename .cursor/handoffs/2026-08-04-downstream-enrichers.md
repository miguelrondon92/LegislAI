# Downstream stakeholder + policy enrichers

Date: 2026-08-04
Status: complete (incl. quota-gate fix)

Owners: Orchestrator → Analysis → Gemini Ops → API → Frontend → QA

## Contract delta

- Added: `policy_areas`, `policy_analysis` (with `status`), template-shaped `stakeholders` (with `status`)
- Core Tier A no longer owns deep policy narrative or stakeholders
- Ops: `enrichment_queued`, `enrichment_finished`
- Migration: no
- display_ready: unchanged (does not wait on enrichments)

## Layers delivered

### Analysis
- Slim Tier A core prompt (summary + categories only)
- `services/analysis_enrichers.py`: stubs, normalize, `run_downstream_enrichments`, `enrichment_quota_ok`

### Gemini Ops
- `ENRICHMENT_QUEUED` / `ENRICHMENT_FINISHED` with `provider_model` + `limit_cause` when deferred

### API
- `_enriching_bill_ids` lock; `_enrichment_defer_until` cooldown; queue after core async + bill detail when pending
- `enrichment_flags` in bill analysis template context

### Frontend
- Policy Areas card (badges)
- Policy Analysis deep-only + pending/skipped placeholders
- Stakeholder Analysis template shape + pending placeholders
- Light auto-poll when enrichment queued

### QA
- `test/test_downstream_enrichers.py` — shape, merge, quota deferral, core independent of enrichments
- size-aware tests still green
- Live verify: Flask restart + `/bill/119/hr/22` showed ready Policy Analysis + Stakeholders

## Follow-up fix (same day): false `local_minute_budget`

Enrichers wrongly read `get_quota_info()["status"]["safe_remaining_requests"]` (key not under `status` → always 0). That caused skip spam in `/ops/logs` and version churn. Fixed via `enrichment_quota_ok()` → `get_rate_limit_status()["remaining_requests"]`; deferrals no longer persist skip versions.

## Handoff: QA → closed

- Change: Downstream enrichers live; UI splits Policy Areas vs Policy Analysis; stakeholders match template; quota gate corrected
- Contract fields: as above — see `pipeline-contract.md`
- display_ready impact: none (enrichments async)
- Suggested tests: `test_downstream_enrichers` + `test_size_aware_analysis` — OK
