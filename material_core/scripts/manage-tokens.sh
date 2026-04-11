#!/usr/bin/env bash
# manage-tokens.sh — Issue, list, and revoke lecture access tokens
#
# Requires environment variables (or a .env file in repo root):
#   CF_ACCOUNT_ID      — Cloudflare account ID (Dashboard → right sidebar)
#   CF_API_TOKEN       — Cloudflare API token with Workers KV edit permission
#   CF_KV_NAMESPACE_ID — KV namespace ID for LECTURE_TOKENS
#
# Usage:
#   ./scripts/manage-tokens.sh issue  <course> <label> [days]
#   ./scripts/manage-tokens.sh list   [course]
#   ./scripts/manage-tokens.sh revoke <token>
#   ./scripts/manage-tokens.sh show   <token>
#
# Examples:
#   ./scripts/manage-tokens.sh issue digital-und-mikrocomputertechnik "WS2025/26" 365
#   ./scripts/manage-tokens.sh issue "*" "Alle Kurse WS2025/26" 365
#   ./scripts/manage-tokens.sh list
#   ./scripts/manage-tokens.sh list digital-und-mikrocomputertechnik
#   ./scripts/manage-tokens.sh revoke abc123xyz
#
# The issued token is printed to stdout — paste it into the Moodle course link:
#   https://material.professorfroehlich.de/<course>/?token=<TOKEN>

set -euo pipefail

# ---------------------------------------------------------------------------
# Load config
# ---------------------------------------------------------------------------

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# Look for .env next to this script first, then at repo root
if [[ -f "$SCRIPT_DIR/.env" ]]; then
  # shellcheck disable=SC1091
  source "$SCRIPT_DIR/.env"
elif [[ -f "$REPO_ROOT/.env" ]]; then
  # shellcheck disable=SC1091
  source "$REPO_ROOT/.env"
fi

: "${CF_ACCOUNT_ID:?Set CF_ACCOUNT_ID}"
: "${CF_API_TOKEN:?Set CF_API_TOKEN}"
: "${CF_KV_NAMESPACE_ID:?Set CF_KV_NAMESPACE_ID}"

KV_BASE="https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/storage/kv/namespaces/${CF_KV_NAMESPACE_ID}"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

cf_get() {
  curl -sSf -H "Authorization: Bearer ${CF_API_TOKEN}" "$@"
}

cf_put() {
  local response http_code
  response=$(curl -sS -w "\n%{http_code}" -X PUT -H "Authorization: Bearer ${CF_API_TOKEN}" "$@")
  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n -1)
  if [[ "$http_code" -lt 200 || "$http_code" -ge 300 ]]; then
    echo "Cloudflare API error (HTTP ${http_code}): ${body}" >&2
    return 1
  fi
}

cf_delete() {
  curl -sSf -X DELETE -H "Authorization: Bearer ${CF_API_TOKEN}" "$@"
}

generate_token() {
  # 24 chars from [a-z0-9] — easy to include in URLs, hard to brute-force
  # head exits before tr finishes; || true prevents pipefail from killing the script
  { LC_ALL=C tr -dc 'a-z0-9' < /dev/urandom || true; } | head -c 24
}

iso_date_offset() {
  local days="$1"
  date -d "+${days} days" "+%Y-%m-%d" 2>/dev/null \
    || date -v "+${days}d" "+%Y-%m-%d"  # macOS fallback
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

cmd_issue() {
  local course="${1:?Usage: issue <course> <label> [days]}"
  local label="${2:?Missing label}"
  local days="${3:-365}"

  local token
  token="$(generate_token)"
  local issued expires
  issued="$(date "+%Y-%m-%d")"
  expires="$(iso_date_offset "$days")"

  local value
  value="$(printf '{"course":"%s","label":"%s","issued":"%s","expires":"%s"}' \
    "$course" "$label" "$issued" "$expires")"

  cf_put "${KV_BASE}/values/tok%3A${token}" \
    -H "Content-Type: application/json" \
    --data-raw "$value" > /dev/null

  echo ""
  echo "Token issued successfully."
  echo ""
  echo "  Token  : ${token}"
  echo "  Course : ${course}"
  echo "  Label  : ${label}"
  echo "  Issued : ${issued}"
  echo "  Expires: ${expires} (${days} days)"
  echo ""
  if [[ "$course" == "*" ]]; then
    echo "  iLearn link (all courses): https://material.professorfroehlich.de/?token=${token}"
  else
    echo "  iLearn link: https://material.professorfroehlich.de/${course}/?token=${token}"
  fi
  echo ""
}

cmd_list() {
  local filter_course="${1:-}"

  local response
  response="$(cf_get "${KV_BASE}/keys?prefix=tok%3A&limit=1000")"

  local keys
  keys="$(echo "$response" | grep -o '"name":"tok:[^"]*"' | sed 's/"name":"tok://;s/"//')"

  if [[ -z "$keys" ]]; then
    echo "No tokens found."
    return 0
  fi

  printf "%-26s %-45s %-20s %-12s %-12s\n" "TOKEN" "COURSE" "LABEL" "ISSUED" "EXPIRES"
  printf "%-26s %-45s %-20s %-12s %-12s\n" "$(printf '%0.s-' {1..26})" "$(printf '%0.s-' {1..45})" "$(printf '%0.s-' {1..20})" "$(printf '%0.s-' {1..12})" "$(printf '%0.s-' {1..12})"

  while IFS= read -r token; do
    local raw
    raw="$(cf_get "${KV_BASE}/values/tok%3A${token}" 2>/dev/null || echo '{}')"
    local course label issued expires
    course="$(echo "$raw" | grep -o '"course":"[^"]*"' | head -1 | sed 's/"course":"//;s/"//')"
    label="$(echo  "$raw" | grep -o '"label":"[^"]*"'  | head -1 | sed 's/"label":"//;s/"//')"
    issued="$(echo "$raw" | grep -o '"issued":"[^"]*"' | head -1 | sed 's/"issued":"//;s/"//')"
    expires="$(echo "$raw"| grep -o '"expires":"[^"]*"'| head -1 | sed 's/"expires":"//;s/"//')"

    if [[ -n "$filter_course" && "$course" != "$filter_course" ]]; then
      continue
    fi

    # Mark expired tokens
    local exp_marker=""
    if [[ -n "$expires" ]] && ! date -d "$expires" > /dev/null 2>&1 || \
       [[ -n "$expires" ]] && [[ "$(date -d "$expires" +%s 2>/dev/null || date -jf "%Y-%m-%d" "$expires" +%s)" -lt "$(date +%s)" ]]; then
      exp_marker=" [EXPIRED]"
    fi

    printf "%-26s %-45s %-20s %-12s %-12s\n" \
      "$token" "$course" "$label" "$issued" "${expires}${exp_marker}"
  done <<< "$keys"
}

cmd_revoke() {
  local token="${1:?Usage: revoke <token>}"

  cf_delete "${KV_BASE}/values/tok%3A${token}" > /dev/null
  echo "Token '${token}' revoked."
}

cmd_show() {
  local token="${1:?Usage: show <token>}"
  local raw
  raw="$(cf_get "${KV_BASE}/values/tok%3A${token}")"
  echo "$raw"
}

# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

cmd="${1:-}"
shift || true

case "$cmd" in
  issue)  cmd_issue  "$@" ;;
  list)   cmd_list   "$@" ;;
  revoke) cmd_revoke "$@" ;;
  show)   cmd_show   "$@" ;;
  *)
    echo "Usage: $0 {issue|list|revoke|show} [args...]"
    echo ""
    echo "  issue  <course> <label> [days=365]"
    echo "  list   [course]"
    echo "  revoke <token>"
    echo "  show   <token>"
    exit 1
    ;;
esac
