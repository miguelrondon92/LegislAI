## Handoff: Analysis / Frontend → QA
Date: 2026-08-04
Status: ready

### Change
- `OpsAlert` model + migration `a1b2c3d4e5f6`
- Persist every Gemini failure; webhook optional
- Dashboard System alerts card + `/ops/logs` with unread/bill/class filters

### Contract delta
- New table: ops_alert
- Migration required: yes

### display_ready impact
none

### Suggested tests
- [x] test_ops_alert_service persist without webhook
- [ ] Manual: open /ops/logs, filter by bill, mark read
