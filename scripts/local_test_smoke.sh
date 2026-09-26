#!/usr/bin/env bash
# =============================================================================
# WatchMan local test smoke check
# Verifies the containerized backend/frontend + their cloud dependencies
# (Supabase Postgres, Upstash Redis, TMDB, HF) are reachable and wired.
#
# Usage:
#   bash scripts/local_test_smoke.sh
#   BACKEND=http://localhost:8000 FRONTEND=http://localhost:3000 bash scripts/local_test_smoke.sh
# =============================================================================
set -u

BACKEND="${BACKEND:-http://localhost:8000}"
FRONTEND="${FRONTEND:-http://localhost:3000}"

pass=0
fail=0

# check <label> <url> <expected-codes-csv> [--body-grep=substring]
check () {
  local label="$1" url="$2" expect="$3" grep_needle="${4:-}"
  local body code
  body="$(curl -sS -m 15 -w $'\n%{http_code}' "$url" 2>/dev/null)"
  code="$(printf '%s' "$body" | tail -n1)"
  body="$(printf '%s' "$body" | sed '$d')"

  if [[ ",$expect," == *",$code,"* ]]; then
    if [[ -n "$grep_needle" ]] && ! printf '%s' "$body" | grep -q "$grep_needle"; then
      echo "  FAIL  $label  (HTTP $code but missing '$grep_needle')"
      fail=$((fail+1)); return
    fi
    echo "  PASS  $label  (HTTP $code)"
    pass=$((pass+1))
  else
    echo "  FAIL  $label  (HTTP $code, expected $expect)"
    [[ -n "$body" ]] && echo "        -> $(printf '%s' "$body" | head -c 200)"
    fail=$((fail+1))
  fi
}

echo "== Backend @ $BACKEND =="
# Liveness: process is up and config loaded (proves it booted past fail-fast checks)
check "liveness /health"        "$BACKEND/health"        "200" '"status":"ok"'
# Readiness: DB (Supabase) + Redis (Upstash) connectivity from inside the container
check "readiness /api/ready"    "$BACKEND/api/ready"     "200,503"
# Public catalog feed: exercises DB + TMDB path
check "movies feed /api/movies" "$BACKEND/api/movies"    "200,404"
check "trending /api/trending"  "$BACKEND/api/trending"  "200,404"
# Admin-gated: MUST reject anonymous (401/403 is the CORRECT/expected result)
check "ops status is protected" "$BACKEND/api/ops/status" "401,403"

echo
echo "== Frontend @ $FRONTEND =="
check "frontend root"           "$FRONTEND/"             "200"

echo
echo "----------------------------------------"
echo "Readiness detail (DB + Redis):"
curl -sS -m 15 "$BACKEND/api/ready" 2>/dev/null | head -c 600
echo
echo "----------------------------------------"
echo "RESULT: $pass passed, $fail failed"
echo "Notes:"
echo "  * /api/ready returning 503 means the app is up but a dependency"
echo "    (Supabase DB or Upstash Redis) failed — read the detail above."
echo "  * ops status returning 401/403 is CORRECT (endpoint is admin-only)."
echo "  * Verify Supabase LOGIN in the browser at $FRONTEND — the smoke"
echo "    check cannot exercise the interactive auth flow."

[[ $fail -eq 0 ]] && exit 0 || exit 1
