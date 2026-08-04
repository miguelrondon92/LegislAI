## Handoff: Analysis / API → QA
Date: 2026-08-04
Status: ready

### Change
- Added `services/ops_alert_service.py` for Gemini failure structured logs + webhook
- Wired analyzer, routes, bill_processor
- Documented OPS_ALERT_* in AGENTS.md, analysis skill, pipeline contract, .env.example

### Contract delta
- none (ops path only)
- Migration required: no

### display_ready impact
none (failures still leave display_ready false)

### Suggested tests
- [x] test_ops_alert_service.py webhook dedup
