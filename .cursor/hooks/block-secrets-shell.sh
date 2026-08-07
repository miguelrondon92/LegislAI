#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_common.sh"

input="$(cat)"
cmd="$(echo "$input" | jq -r '.command // .tool_input.command // empty')"

if [[ -z "$cmd" ]]; then
  allow_json
  exit 0
fi

if command_touches_secrets "$cmd"; then
  deny_json \
    "Blocked: shell command may expose secrets or private keys." \
    "Shell command denied by LegislAI secrets hook. Do not cat .env, printenv, or dump API keys. Reference variable names and .env.example only."
  exit 0
fi

allow_json
exit 0
