#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
status="$(echo "$input" | jq -r '.status // .subagent_status // empty')"
summary="$(echo "$input" | jq -r '.summary // .result // .message // empty' | head -c 500)"

# Encourage pipeline continuation after a specialist finishes.
followup="LegislAI pipeline check: if this subagent changed ETL, schema, analysis JSON, routes, or templates, run skill legislai-pipeline-handoff and continue the next owner in order (ETL -> Database -> Analysis -> API -> Frontend -> QA). Do not read .env or secrets. Prior summary: ${summary:-"(none)"}"

jq -n --arg m "$followup" '{followup_message:$m}'
