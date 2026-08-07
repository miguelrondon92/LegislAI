#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=/dev/null
source "$DIR/_common.sh"

input="$(cat)"
# preToolUse for Write/Read — inspect path in tool_input
path="$(echo "$input" | jq -r '.tool_input.path // .tool_input.file_path // .path // .file_path // empty')"
tool="$(echo "$input" | jq -r '.tool_name // .tool // empty')"

if [[ -n "$path" ]] && is_secret_path "$path"; then
  deny_json \
    "Blocked: agents cannot read or write secret files ($path)." \
    "Tool $tool on secret path denied. Use .env.example / templates only."
  exit 0
fi

# Also scan Write contents for private key material
contents="$(echo "$input" | jq -r '.tool_input.contents // .tool_input.content // empty')"
if [[ -n "$contents" ]]; then
  if echo "$contents" | grep -Eiq 'BEGIN (RSA |OPENSSH |EC |PGP )?PRIVATE KEY|AKIA[0-9A-Z]{16}'; then
    deny_json \
      "Blocked: write appears to contain private key material." \
      "Refusing to write private key material into the repository."
    exit 0
  fi
fi

allow_json
exit 0
