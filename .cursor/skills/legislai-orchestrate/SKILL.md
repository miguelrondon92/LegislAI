---
name: legislai-orchestrate
description: Coordinate multi-layer LegislAI features across ETL, database, analysis, API, frontend, and QA. Use when a change spans ingestion through UI, when subagents must collaborate, or when the user asks to implement an end-to-end LegislAI feature.
---

# LegislAI Orchestrate

## When to use

Any task that touches **two or more** of: ETL, DB schema, AI analysis, routes, templates.

## Protocol

1. Read `AGENTS.md` and `.cursor/resources/pipeline-contract.md`.
2. Write a one-paragraph plan naming owners in order.
3. Execute layers **in order** (skip untouched layers):

```
ETL → Database → Analysis → Gemini Ops (when quota/model/ops-log) → API → Frontend → QA
```

When work involves `GEMINI_MODEL`, OpsAlert lifecycle, or `/ops/logs`, include **Gemini Ops** after Analysis writers (or in parallel with Frontend for ops UI badges).

4. After each layer, run skill `legislai-pipeline-handoff` (or write the packet yourself).
5. Do not mark complete until QA confirms `display_ready` / UI path (and, when relevant, enrichment cards or honest pending state).
6. After code changes that affect the running app: **restart Flask and verify** the affected URLs yourself before telling the user to refresh.

## Subagent spawning

When using Task/subagents, give each:

- Role name from `.cursor/resources/agent-roster.md`
- Exact file globs
- The prior handoff packet
- Explicit **secrets ban**

Example sequence for “add a new analysis field shown on bill detail”:

1. Analysis proposes JSON key + storage (core vs async enricher?)
2. Database adds column/JSON contract if needed + migration
3. Analysis writes the field (stamp `provider_model` when Gemini-produced)
4. Gemini Ops if ops logs / model constant / quota messaging is touched
5. API exposes it in bill detail context
6. Frontend renders it
7. QA adds/extends a test

For stakeholder / deep policy work: prefer **async enrichers** (`services/analysis_enrichers.py`) so core Tier A stays ~2 calls and `display_ready` stays fast.

## Conflict resolution

- Schema disputes → Database agent wins on storage; Analysis wins on JSON semantics only inside `analysis_data` unless indexed/queryable fields are required
- UI copy vs data → Frontend owns presentation; cannot invent missing data
- Rate limits / fetch → ETL owns Congress; Gemini Ops owns Gemini free-tier narrative / OpsAlert; Analysis must tolerate partial data
- `GEMINI_MODEL` constant → Gemini Ops; stamping onto analysis rows → Analysis
- Quota reads for enrichers → use `enrichment_quota_ok` / `get_rate_limit_status`, never `get_quota_info()["status"]["safe_remaining_requests"]`

## Secrets

Never read `.env` or keys. Orchestrator must not ask subagents to dump env.
