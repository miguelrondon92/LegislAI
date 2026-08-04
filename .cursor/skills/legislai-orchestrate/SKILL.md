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
ETL → Database → Analysis → API → Frontend → QA
```

4. After each layer, run skill `legislai-pipeline-handoff` (or write the packet yourself).
5. Do not mark complete until QA confirms `display_ready` / UI path.

## Subagent spawning

When using Task/subagents, give each:

- Role name from `.cursor/resources/agent-roster.md`
- Exact file globs
- The prior handoff packet
- Explicit **secrets ban**

Example sequence for “add a new analysis field shown on bill detail”:

1. Analysis proposes JSON key + storage
2. Database adds column/JSON contract if needed + migration
3. Analysis writes the field
4. API exposes it in bill detail context
5. Frontend renders it
6. QA adds/extends a test

## Conflict resolution

- Schema disputes → Database agent wins on storage; Analysis wins on JSON semantics only inside `analysis_data` unless indexed/queryable fields are required
- UI copy vs data → Frontend owns presentation; cannot invent missing data
- Rate limits / fetch → ETL owns; Analysis must tolerate partial data

## Secrets

Never read `.env` or keys. Orchestrator must not ask subagents to dump env.
