#!/usr/bin/env bash
set -euo pipefail

# sessionStart: inject agentic architecture context (no secrets).
cat <<'EOF'
{
  "additional_context": "LegislAI agentic mode active. Roster: Orchestrator, ETL, Database, Analysis, API/Routes, Frontend, QA. Pipeline: ETL → Database → Analysis → API → Frontend → QA. Contracts: .cursor/resources/pipeline-contract.md, display-ready-contract.md, schema-surface.md, agent-roster.md. Skills: legislai-orchestrate, legislai-etl, legislai-database, legislai-analysis, legislai-frontend, legislai-pipeline-handoff, legislai-qa. SECRETS BAN: never read .env, *.pem, *.key, or credential files — use .env.example only. After layer changes, emit a handoff packet."
}
EOF
