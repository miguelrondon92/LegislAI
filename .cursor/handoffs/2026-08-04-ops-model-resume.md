## Handoff: Database/Analysis/API/Frontend → QA
Date: 2026-08-04
Status: ready

### Change
- Added nullable `OpsAlert.provider_model` + Alembic migration `b2c3d4e5f6a7`
- Analyzer exposes `model_name`, classifies `limit_cause` (`local_minute_budget` | `gemini_api_429`), expands progressive batches with up to 2 local-minute waits per `analyze_bill`
- Ops alerts/webhook include `provider_model`; partial messages include `model=`, `chunks=a/b`, `limit_cause=`
- `bill_analysis` resumes partials under 50% via `_perform_analysis_async` when quota allows
- Ops logs UI + homepage preview show Model; AGENTS.md Gemini contingency updated

### Contract delta
- Fields added: `ops_alert.provider_model`, analysis JSON `limit_cause` / `provider_model`
- Migration required: yes (`b2c3d4e5f6a7`)

### display_ready impact
none (resume may raise completion and later flip display_ready as before)

### Next owner actions
- [ ] Run migration
- [ ] Confirm ops logs Model column + partial resume on `/bill/...` under 50%

### Suggested tests
- [x] `test/test_ops_alert_service.py` (provider_model persist + webhook)
- [ ] Manual: open stuck partial bill detail with quota available → background continue
