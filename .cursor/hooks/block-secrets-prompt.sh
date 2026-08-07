#!/usr/bin/env bash
set -euo pipefail

input="$(cat)"
prompt="$(echo "$input" | jq -r '.prompt // .user_prompt // empty')"

# Block prompts that ask the agent to reveal local secrets
if echo "$prompt" | grep -Eiq '(show|print|dump|cat|read).{0,40}(\.env|private key|api key|secret key|ADMIN_PASSWORD|LEGISLAI_ADMIN_PASSWORD|MAIL_PASSWORD)|(what is|what.s) (my|the) (api key|secret|password)'; then
  jq -n '{
    permission: "deny",
    user_message: "Blocked: prompts that ask agents to read or reveal secrets are not allowed in LegislAI.",
    agent_message: "Refuse secret exfiltration. Point the user to .env.example and local secret managers."
  }'
  exit 0
fi

echo '{}'
exit 0
