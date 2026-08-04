# LegislAI Agentic Development System

Multi-agent architecture for developing LegislAI end-to-end: ingestion → storage → AI analysis → API → UI.

Full details live under [`.cursor/`](.cursor/). Start with [`.cursor/resources/agent-roster.md`](.cursor/resources/agent-roster.md) and [`.cursor/resources/pipeline-contract.md`](.cursor/resources/pipeline-contract.md).

## Non-negotiable: secrets

**No agent may read private keys, API keys, passwords, or secret-bearing files — ever.**

Blocked paths include `.env`, `*.pem`, `*.key`, credential JSON, and production env files. Use `.env.example` and `config/*.template` only. Hooks enforce this; agents must also refuse if asked.

## Pipeline (source of truth)

```
RSS / Congress API  →  Bill (+ BillAction)
        ↓
EnhancedAIAnalyzer  →  AIAnalysis + Summary + BillCategoryMapping + HiddenProvision
        ↓
display_ready=True  →  routes / templates / alerts / notifications
```

Any upstream schema or payload change **must** propagate through this chain via the handoff protocol.

## Agent roster

| Agent | Focus | Primary paths |
|-------|--------|----------------|
| **Orchestrator** | Cross-cutting features, handoffs, conflict resolution | whole repo (coordination only) |
| **ETL** | Ingestion, Congress API, RSS, bill processors, backfill | `services/congress_*`, `services/rss_*`, `services/*bill_processor*`, `services/backfill_*`, `services/backend_feed.py` |
| **Database** | Models, migrations, indexes, versioning | `db_models.py`, `migrations/`, `manage.py` |
| **Analysis** | Gemini analysis, chunking, categories, hidden provisions | `services/enhanced_ai_analyzer.py`, `services/analysis_*`, `utils/bill_chunker.py`, `utils/text_processing.py` |
| **API / Routes** | Flask routes, auth, workflow admin APIs | `routes.py`, `auth.py`, `app.py`, `workflow_admin.py` |
| **Frontend** | Jinja templates, CSS, JS, display-ready UX | `templates/`, `static/` |
| **QA** | Tests, fixtures, regression for pipeline | `test/`, root `test_*.py` |

## How to run work

1. Load skill `legislai-orchestrate` for multi-layer changes.
2. Spawn specialized subagents (or sequential turns) per layer touched.
3. After each layer finishes, run skill `legislai-pipeline-handoff` and notify the next owner.
4. QA validates `display_ready` and UI surface before closing.

## Skills

| Skill | When |
|-------|------|
| `legislai-orchestrate` | Feature spans 2+ layers |
| `legislai-etl` | Ingestion / Congress / RSS / backfill |
| `legislai-database` | Schema / migrations / model methods |
| `legislai-analysis` | AI analyzer / categories / hidden provisions |
| `legislai-frontend` | Templates / static / progressive loading |
| `legislai-pipeline-handoff` | After any layer change that affects downstream |
| `legislai-qa` | Verification and regression |

## Docs map

- Architecture: `docs/CLAUDE.md`
- Structure: `PROJECT_STRUCTURE.md`
- Workflow: `docs/WORKFLOW_README.md`
- Bill search: `docs/BILL_SEARCH_WORKFLOW_GUIDE.md`
- DB: `docs/DATABASE_OPTIMIZATION_SUMMARY.md`, `docs/DATABASE_POPULATION_GUIDE.md`
- Analysis pipeline: `docs/ENHANCED_ANALYSIS_PIPELINE_DOCUMENTATION.md`
