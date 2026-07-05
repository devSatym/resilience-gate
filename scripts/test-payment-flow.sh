#!/usr/bin/env bash
# Exercise the current x402 v2 / Permit2 protocol against an owned testnet.
#
# This intentionally performs one settled testnet payment when enabled. It is
# not a CI test and refuses to run unless the operator explicitly opts in.
set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
SIGNER_URL="${SIGNER_URL:-http://localhost:8080}"
WALLET_INDEX="${WALLET_INDEX:-0}"
REQUEST_TIMEOUT_SECONDS="${REQUEST_TIMEOUT_SECONDS:-20}"
TEST_URL="${TEST_URL:-https://example.com/resilience-gate-payment-$(date +%s)-$$}"
REPLAY_URL="${REPLAY_URL:-${TEST_URL}/replay}"

usage() {
  cat <<'EOF'
Usage:
  RUN_TESTNET_PAYMENTS=1 ./scripts/test-payment-flow.sh

Required services:
  - a payment-enabled URL API at BASE_URL (default http://localhost:8000)
  - a bootstrapped Permit2 signer at SIGNER_URL (default http://localhost:8080)

Optional variables: BASE_URL, SIGNER_URL, WALLET_INDEX, TEST_URL, REPLAY_URL,
REQUEST_TIMEOUT_SECONDS. The script creates one new testnet payment and then
reuses its authorization with a different URL to verify replay handling.
EOF
}

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "required command is missing: $1"
}

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  usage
  exit 0
fi

if [[ "${RUN_TESTNET_PAYMENTS:-}" != "1" ]]; then
  usage >&2
  fail "set RUN_TESTNET_PAYMENTS=1 to authorize a real testnet settlement"
fi

require_command curl
require_command jq
require_command base64
require_command awk

[[ "$WALLET_INDEX" =~ ^[0-9]+$ ]] || fail "WALLET_INDEX must be a non-negative integer"
[[ "$REQUEST_TIMEOUT_SECONDS" =~ ^[1-9][0-9]*$ ]] || fail "REQUEST_TIMEOUT_SECONDS must be positive"
[[ "$TEST_URL" != "$REPLAY_URL" ]] || fail "REPLAY_URL must differ from TEST_URL"

work_dir=$(mktemp -d)
headers_402="$work_dir/headers-402"
body_402="$work_dir/body-402"
signer_body="$work_dir/signer-body"
headers_201="$work_dir/headers-201"
body_201="$work_dir/body-201"
headers_replay="$work_dir/headers-replay"
body_replay="$work_dir/body-replay"

cleanup() {
  rm -f "$headers_402" "$body_402" "$signer_body" "$headers_201" "$body_201" \
    "$headers_replay" "$body_replay"
  rmdir "$work_dir" 2>/dev/null || true
}
trap cleanup EXIT

post_shorten() {
  local target_url=$1
  local header_file=$2
  local body_file=$3
  local payment_header=${4:-}
  local request_body
  request_body=$(jq -cn --arg url "$target_url" '{url: $url}')

  local curl_args=(
    curl --silent --show-error
    --connect-timeout "$REQUEST_TIMEOUT_SECONDS"
    --max-time "$REQUEST_TIMEOUT_SECONDS"
    --dump-header "$header_file"
    --output "$body_file"
    --write-out '%{http_code}'
    --request POST "${BASE_URL%/}/shorten"
    --header 'Content-Type: application/json'
    --data "$request_body"
  )
  if [[ -n "$payment_header" ]]; then
    curl_args+=(--header "PAYMENT-SIGNATURE: $payment_header")
  fi
  "${curl_args[@]}"
}

header_value() {
  local header_name=$1
  local header_file=$2
  awk -v wanted="${header_name,,}" '
    tolower($1) == wanted ":" {
      sub(/^[^:]*:[[:space:]]*/, "")
      value = $0
    }
    END {
      gsub(/\r/, "", value)
      print value
    }
  ' "$header_file"
}

echo "Checking payment challenge at ${BASE_URL%/}/shorten"
status_402=$(post_shorten "$TEST_URL" "$headers_402" "$body_402")
[[ "$status_402" == "402" ]] || {
  cat "$body_402" >&2 || true
  fail "expected 402 from a new unpaid URL, got HTTP $status_402; use a unique TEST_URL"
}

payment_required=$(header_value 'payment-required' "$headers_402")
[[ -n "$payment_required" ]] || fail "402 response did not include PAYMENT-REQUIRED"
required_json=$(printf '%s' "$payment_required" | base64 --decode)
printf '%s' "$required_json" | jq -e '.x402Version == 2 and (.accepts | length > 0)' >/dev/null \
  || fail "PAYMENT-REQUIRED is not a usable x402 v2 challenge"
accepted=$(printf '%s' "$required_json" | jq -ec '.accepts[0]')
amount=$(printf '%s' "$accepted" | jq -er '.amount')
[[ "$amount" =~ ^[1-9][0-9]*$ ]] || fail "challenge amount must be a positive integer"

echo "Requesting a Permit2 authorization from ${SIGNER_URL%/}/sign-permit2"
sign_request=$(jq -cn --argjson wallet_index "$WALLET_INDEX" --argjson amount "$amount" \
  '{wallet_index: $wallet_index, amount: $amount}')
sign_status=$(curl --silent --show-error \
  --connect-timeout "$REQUEST_TIMEOUT_SECONDS" \
  --max-time "$REQUEST_TIMEOUT_SECONDS" \
  --output "$signer_body" \
  --write-out '%{http_code}' \
  --request POST "${SIGNER_URL%/}/sign-permit2" \
  --header 'Content-Type: application/json' \
  --data "$sign_request")
[[ "$sign_status" == "200" ]] || {
  cat "$signer_body" >&2 || true
  fail "signer returned HTTP $sign_status"
}

signature=$(jq -er '.signature | select(type == "string" and startswith("0x"))' "$signer_body")
authorization=$(jq -ec '.permit2Authorization | select(type == "object")' "$signer_body")
payment_envelope=$(jq -cn \
  --argjson accepted "$accepted" \
  --arg signature "$signature" \
  --argjson authorization "$authorization" \
  '{x402Version: 2, accepted: $accepted, payload: {signature: $signature, permit2Authorization: $authorization}}')
payment_signature=$(printf '%s' "$payment_envelope" | base64 | tr -d '\n')

echo "Submitting one signed testnet payment"
status_201=$(post_shorten "$TEST_URL" "$headers_201" "$body_201" "$payment_signature")
[[ "$status_201" == "201" ]] || {
  cat "$body_201" >&2 || true
  fail "expected 201 after a valid signer response, got HTTP $status_201"
}
printf '%s\n' "Created: $(jq -c . "$body_201")"

echo "Replaying the same authorization against a second URL"
status_replay=$(post_shorten "$REPLAY_URL" "$headers_replay" "$body_replay" "$payment_signature")
[[ "$status_replay" == "409" ]] || {
  cat "$body_replay" >&2 || true
  fail "expected 409 for replayed settlement, got HTTP $status_replay"
}

echo "PASS: challenge (402), signed settlement (201), and replay guard (409) behaved as expected."
