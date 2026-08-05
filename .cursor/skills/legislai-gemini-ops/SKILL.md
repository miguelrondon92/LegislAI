---
name: legislai-gemini-ops
description: Own Gemini model constant, OpsAlert lifecycle, free-tier quota awareness, and /ops/logs visibility. Use for GEMINI_MODEL changes, ops alerts, quota probes, continuation and enrichment lifecycle events.
---

# LegislAI Gemini Ops

## When to use

- Changing `utils.constants.GEMINI_MODEL`
- Ops alerts / `/ops/logs` / homepage system-alert preview
- Quota probes (`scripts/debug/check_gemini_quota.py`)
- Resume lifecycle events (`continuation_queued` / `continuation_finished`)
- Enrichment lifecycle (`enrichment_queued` / `enrichment_finished`)
- Interpreting `limit_cause` (`local_minute_budget` vs `gemini_api_429`)

## Free-tier constraints (Google AI Studio)

| Limit | Typical value | App implication |
|-------|---------------|-----------------|
| RPM | **15–30** (varies by model) | Local limiter stays at **15** RPM |
| RPD | **~1,500** / project | No local RPD counter; daily exhaustion surfaces as API 429 |
| Daily reset | **Midnight Pacific Time** | Document only; do not invent a local RPD scheduler |
| Over limit | HTTP **429** `RESOURCE_EXHAUSTED` | Classify as `quota_exhausted` / `limit_cause=gemini_api_429` |
| Privacy | Free-tier prompts may train Google products | Note for programmers; never log secrets |

## Responsibilities

1. Keep `GEMINI_MODEL` and `OpsAlert.provider_model` defaults aligned.
2. Require lifecycle OpsAlerts on resume: queue → `continuation_queued` (info); finish → `continuation_finished` (info/warning/error).
3. Require enrichment OpsAlerts: `enrichment_queued` / `enrichment_finished` (include `provider_model`; on RPM deferral include `limit_cause=local_minute_budget` and `remaining_requests`).
4. Probe models via `check_gemini_quota.py` using `GEMINI_MODEL` — never print API keys.
5. Coordinate with Analysis: Analysis **stamps** `provider_model` on `AIAnalysis` / `Summary` / `HiddenProvision` at write time; Gemini Ops owns changing the constant.
6. Document quota-read pitfalls: enrichers must use `enrichment_quota_ok` / `get_rate_limit_status`, not `get_quota_info()["status"]["safe_remaining_requests"]`.

## Rules

- Never read `.env` or log secret values.
- Do not raise local RPM above 15 without an explicit paid-tier decision.
- Cross-edit `enhanced_ai_analyzer.py` / `analysis_enrichers.py` notify sites only when wiring ops events; leave chunking/prompt semantics to Analysis.
- Ops UI must style `severity=info` distinctly from warning/error.
- After ops/route/analyzer changes: restart Flask and verify `/ops/logs` + a sample `/bill/...` yourself.

## Handoff

| Change | Notify |
|--------|--------|
| `GEMINI_MODEL` swap | Analysis (stamp + probe) + QA |
| New failure_class | Frontend (filters/badges) + QA |
| Ops template change | Frontend ownership overlap OK |

## References

- `services/ops_alert_service.py`
- `services/analysis_enrichers.py` (`enrichment_quota_ok`)
- `utils/constants.py` (`GEMINI_MODEL`)
- `templates/ops_logs.html`, `templates/index.html` (system alerts)
- `scripts/debug/check_gemini_quota.py`
- `AGENTS.md` Gemini contingency
