# LegislAI documentation index

**Start here:** [root README](../README.md) — product overview, fine-tuning, architecture chart.

Service diagrams: [services/README.md](../services/README.md).  
Agent / pipeline source of truth: [AGENTS.md](../AGENTS.md), [pipeline-contract](../.cursor/resources/pipeline-contract.md).

## Current docs

| File | Description |
|------|-------------|
| [`CLAUDE.md`](./CLAUDE.md) | Longer developer guide (defers to AGENTS on pipeline) |
| [`RECENT_UPDATES.md`](./RECENT_UPDATES.md) | Chronological product/engineering updates |
| [`ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md`](./ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md) | Tier A/B analysis, hidden provisions, rate limits |
| [`WORKFLOW_README.md`](./WORKFLOW_README.md) | RSS workflow orchestrator and API |
| [`DATABASE_POPULATION_GUIDE.md`](./DATABASE_POPULATION_GUIDE.md) | Populating congressional data |
| [`DATABASE_OPTIMIZATION_SUMMARY.md`](./DATABASE_OPTIMIZATION_SUMMARY.md) | AIAnalysis / Summary normalization overview |
| [`PRODUCTION_BACKFILL_GUIDE.md`](./PRODUCTION_BACKFILL_GUIDE.md) | Production backfill with PostgreSQL |
| [`NOTIFICATION_ENVIRONMENT_CONTROLS.md`](./NOTIFICATION_ENVIRONMENT_CONTROLS.md) | `NOTIFICATIONS_ENABLED` / env gating |

## Archived docs

Historical implementation summaries and fix logs live under [`archives/docs/`](../archives/docs/). Prefer the root README and pipeline contract when those conflict with archived notes.

## Related

| Path | Description |
|------|-------------|
| [`PROJECT_STRUCTURE.md`](../PROJECT_STRUCTURE.md) | Directory layout |
| [`config/README.md`](../config/README.md) | Env templates |
| [`scripts/README.md`](../scripts/README.md) | Setup / debug / cleanup scripts |
| [`.cursor/README.md`](../.cursor/README.md) | Agentic Cursor system |

## Contributing to documentation

1. Update [root README](../README.md) or [services/README.md](../services/README.md) for architecture / product changes.
2. Update [AGENTS.md](../AGENTS.md) / pipeline-contract for agent-facing pipeline rules.
3. Append noteworthy shipped work to [`RECENT_UPDATES.md`](./RECENT_UPDATES.md).
4. Do not revive archived fix logs as current architecture — add a short current doc or extend the README instead.
