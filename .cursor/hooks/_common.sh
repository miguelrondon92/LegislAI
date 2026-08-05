#!/usr/bin/env bash
# Shared helpers for LegislAI Cursor hooks (source from other scripts).

is_secret_path() {
  local path="$1"
  path="${path//\\/\/}"
  local base
  base="$(basename "$path")"

  case "$path" in
    *.env|*/.env|*/.env.*|.env|.env.*)
      # allow templates
      case "$base" in
        .env.example|*.example|*.template) return 1 ;;
      esac
      return 0
      ;;
  esac

  case "$base" in
    .env|.env.*|*.pem|*.key|id_rsa|id_rsa.*|*credentials*.json|*firebase-adminsdk*.json|serviceAccount*.json|production.env|production_email_config.env)
      case "$base" in
        .env.example|*.example|*.template) return 1 ;;
      esac
      return 0
      ;;
  esac

  case "$path" in
    */config/production.env|*/config/production_email_config.env)
      return 0
      ;;
  esac

  return 1
}

command_touches_secrets() {
  local cmd="$1"
  # Explicit secret file reads / dumps
  if echo "$cmd" | grep -Eiq '(cat|less|more|head|tail|bat|hexdump|xxd|nl)\>.*(\.env|/production\.env|production_email_config\.env|\.pem|\.key|id_rsa|credentials\.json|firebase-adminsdk|serviceAccount)'; then
    return 0
  fi
  if echo "$cmd" | grep -Eiq '(^|[;&|[:space:]])(printenv|env)([|;[:space:]]|$)'; then
    return 0
  fi
  if echo "$cmd" | grep -Eiq '(echo|printf|print)\>.*(_API_KEY|SECRET_KEY|MAIL_PASSWORD|ADMIN_PASSWORD|LEGISLAI_ADMIN_PASSWORD)'; then
    return 0
  fi
  if echo "$cmd" | grep -Eiq 'export[[:space:]]+[A-Za-z0-9_]*(KEY|PASSWORD|SECRET)='; then
    return 0
  fi
  if echo "$cmd" | grep -Eiq 'base64\>.*\.(env|pem|key)|openssl[[:space:]]+(rsa|ec)|ssh-keygen.*-y'; then
    return 0
  fi
  if echo "$cmd" | grep -Eiq 'python[0-9.]*[^|;]*os\.environ|python[0-9.]*[^|;]*load_dotenv'; then
    return 0
  fi
  return 1
}

deny_json() {
  local user_msg="$1"
  local agent_msg="$2"
  jq -n \
    --arg u "$user_msg" \
    --arg a "$agent_msg" \
    '{permission:"deny",user_message:$u,agent_message:$a}'
}

allow_json() {
  echo '{"permission":"allow"}'
}
