#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_common.sh"

input="$(cat)"
# beforeReadFile payload variants: file_path, path, or tool_input.path
path="$(echo "$input" | jq -r '.file_path // .path // .tool_input.path // .tool_input.file_path // empty')"

if [[ -z "$path" ]]; then
  allow_json
  exit 0
fi

if is_secret_path "$path"; then
  deny_json \
    "Blocked: agents cannot read secret files ($path). Use .env.example or config templates." \
    "Secret file read denied by LegislAI hook. Use .env.example / *.template only. Never read private keys or .env."
  exit 0
fi

allow_json
exit 0
