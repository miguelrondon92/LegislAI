## Handoff: Cleanup → QA / ETL
Date: 2026-08-05
Status: ready

### Change
- Deleted unused stubs: `services/enhanced_bill_processor.py`, `services/backend_feed.py`, `services/analysis_cache.py`
- Scrubbed agent docs: `AGENTS.md`, `.cursor/resources/agent-roster.md`, `.cursor/skills/legislai-etl/SKILL.md`, `.cursor/rules/etl-agent.mdc`
- Also removed phantom `analysis_session_scheduler.py` from Analysis agent roster (file never existed)

### Contract delta
- none
- Migration required: no

### display_ready impact
none

### Follow-up smoke (do not skip)
- [ ] Bill search: `POST /bill_search` (e.g. HR22) + `GET /bill/119/hr/22` — no missing-module errors
- [ ] App imports: `CongressAPI`, `PersistentRSSMonitor`, `WorkflowBillProcessor`, `BackfillOrchestrator` (via app context)
- [ ] Workflow: `GET /api/workflow/status` (optional start/stop) still works
- [ ] Backfill CLI: `python services/backfill_orchestrator.py --help` or `--status`
- [ ] Grep: no live refs to deleted modules outside `backup_old_analyzers/`

### Suggested tests
- Manual smoke above; no new unit tests required for deletion-only change
