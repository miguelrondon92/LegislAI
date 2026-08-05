# LegislAI Cursor Agentic System

Project-local Cursor configuration for multi-agent LegislAI development.

## Layout

| Path | Purpose |
|------|---------|
| `hooks.json` | Hook registration (secrets + pipeline) |
| `hooks/` | Executable hook scripts |
| `rules/` | Always-on + path-scoped agent rules |
| `skills/` | Domain skills for orchestrator and specialists |
| `resources/` | Shared contracts (pipeline, schema, display_ready, roster) |
| `handoffs/` | Written handoff packets between agents |

## Enabling

Cursor loads project hooks from `.cursor/hooks.json` automatically. Confirm in **Cursor Settings → Hooks**. Restart Cursor if hooks do not appear after the first add.

Skills under `.cursor/skills/*/SKILL.md` are project skills. Rules under `.cursor/rules/*.mdc` apply per frontmatter.

## Security model

Fail-closed hooks block:

- Reading `.env` and private key / credential files
- Shell commands that dump env or secret files
- Writes containing private key PEM material
- Prompts that ask to reveal secrets (best-effort)

Allowed references: `.env.example`, `config/*.template`, `config/*.example`.

## Orchestration

Use skill **legislai-orchestrate** for cross-layer work. Subagent completion triggers a pipeline follow-up reminder via `subagentStop`.

Shared contracts under `resources/`:

- `pipeline-contract.md` — analysis JSON, Tier A/B, enrichments, ops classes
- `display-ready-contract.md` — what gates homepage (enrichments are **not** required)
- `schema-surface.md` — tables + enrichment JSON note
- `agent-roster.md` — owners and file globs

After analysis/route/template changes: restart Flask and verify `/bill/...` + `/ops/logs` before closing a handoff.
