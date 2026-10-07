#!/usr/bin/env bash
# VS-012 post-deploy smoke check (partitioned audit log, audit-log viewer, BUG-39).
#
# Usage:
#   Local docker compose stack:  scripts/smoke/vs012_post_deploy.sh
#   Live site:                   READONLY_DATABASE_URL=postgresql://ro_user@host/db \
#                                API_LOG_CMD="<print recent api logs>" \
#                                WORKER_LOG_CMD="<print recent worker logs>" \
#                                scripts/smoke/vs012_post_deploy.sh https://<site>
#   Optional: EXPECTED_MIN_AUDIT_ROWS=<audit_logs count taken just before the deploy>
#
# READ-ONLY. It sends only GET requests, and only anonymous ones, which the
# admin boundary refuses before anything is written (not even a rate-limit
# counter). Every SQL statement runs inside BEGIN TRANSACTION READ ONLY ...
# ROLLBACK, so PostgreSQL itself refuses any write. Exit status 0 = all passed.

set -uo pipefail

BASE_URL="${1:-http://localhost:8000}"
BASE_URL="${BASE_URL%/}"
if [ -n "${READONLY_DATABASE_URL:-}" ]; then
  MODE="remote"
else
  MODE="local"
  # --tail, not --since: --since compares against the Docker VM's clock, which
  # can drift from the host's and then silently returns nothing.
  API_LOG_CMD="${API_LOG_CMD:-docker compose logs --no-log-prefix --tail 200 api}"
  WORKER_LOG_CMD="${WORKER_LOG_CMD:-docker compose logs --no-log-prefix worker}"
fi

FAILED=0
pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILED=1; }
info() { printf 'INFO  %s\n' "$*"; }
skip() { printf 'SKIP  %s\n' "$*"; }

# One read-only query; prints rows unaligned, or __ERROR__ if psql failed.
sql() {
  local out
  if [ "$MODE" = "remote" ]; then
    out=$(psql "$READONLY_DATABASE_URL" -XAtq -v ON_ERROR_STOP=1 \
      -c "BEGIN TRANSACTION READ ONLY" -c "$1" -c "ROLLBACK" 2>&1) || out="__ERROR__ $out"
  else
    # shellcheck disable=SC2016 # $POSTGRES_* expand inside the container.
    out=$(docker compose exec -T postgres sh -c \
      'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -XAtq -v ON_ERROR_STOP=1 \
        -c "BEGIN TRANSACTION READ ONLY" -c "$1" -c "ROLLBACK"' sh "$1" 2>&1) \
      || out="__ERROR__ $out"
  fi
  printf '%s' "$out"
}

# GET; prints "<status> <body>".
get() {
  local body status
  body=$(mktemp)
  status=$(curl -s -o "$body" -w '%{http_code}' --max-time 10 "$BASE_URL$1") || status="000"
  printf '%s %s' "$status" "$(cat "$body")"
  rm -f "$body"
}

echo "VS-012 post-deploy check against $BASE_URL ($MODE)"

# 1. The app is up -------------------------------------------------------------
for path in /health/live /health/ready; do
  status=$(get "$path" | cut -d' ' -f1)
  [ "$status" = 200 ] && pass "$path -> 200" || fail "$path -> $status"
done

# 2. A logged-out caller cannot open the audit log ---------------------------------
for path in /api/v1/admin/audit-logs /api/v1/admin/audit-logs/00000000-0000-0000-0000-000000000000; do
  response=$(get "$path")
  if [ "${response%% *}" = 401 ] && [[ "$response" == *'"code":"AUTH_REQUIRED"'* ]]; then
    pass "anonymous GET $path -> 401 AUTH_REQUIRED"
  else
    fail "anonymous GET $path -> ${response:0:120}"
  fi
done

# 3. An email search never reaches the access log -----------------------------------
# Anonymous, so it is refused (401) and writes nothing - but uvicorn logs the
# request line all the same, which is exactly what the filter must clean.
probe="vs012-smoke-probe-$RANDOM$RANDOM"
get "/api/v1/admin/users?search=$probe%40example.invalid" >/dev/null
if [ -n "${API_LOG_CMD:-}" ]; then
  sleep 2
  logs=$($API_LOG_CMD 2>&1)
  if [[ "$logs" == *"$probe"* ]]; then
    fail "the searched email is in the api access log"
  elif [[ "$logs" == *'"GET /api/v1/admin/users HTTP/1.1" 401'* ]]; then
    pass "the search was logged without its query string"
  else
    fail "the probe request is not in the api log at all - is API_LOG_CMD right?"
  fi
else
  skip "access log (set API_LOG_CMD)"
fi

# 4. ensure_partitions has not failed in the worker ---------------------------------
if [ -n "${WORKER_LOG_CMD:-}" ]; then
  if $WORKER_LOG_CMD 2>&1 | grep -q "ensure_partitions_failed"; then
    fail "the worker logged ensure_partitions_failed"
  else
    pass "no ensure_partitions_failed in the worker log"
  fi
else
  skip "worker log (set WORKER_LOG_CMD)"
fi

# 5. Database, read-only ---------------------------------------------------------
kind=$(sql "SELECT relkind FROM pg_class WHERE relname = 'audit_logs'")
if [ "$kind" = p ]; then
  pass "audit_logs is a partitioned table"

  missing=$(sql "
    SELECT string_agg(w.name, ' ' ORDER BY w.name)
    FROM (
      SELECT 'audit_logs_y' || to_char(
               date_trunc('month', now() AT TIME ZONE 'UTC') + make_interval(months => n),
               'YYYY\"m\"MM') AS name
      FROM generate_series(0, 3) AS n
    ) AS w
    WHERE NOT EXISTS (
      SELECT 1 FROM pg_inherits i JOIN pg_class c ON c.oid = i.inhrelid
      WHERE i.inhparent = 'audit_logs'::regclass AND c.relname = w.name
    )")
  [ -z "$missing" ] && pass "partitions exist for the current month and the next 3" \
    || fail "missing partitions: $missing"

  default=$(sql "SELECT count(*) FROM pg_partitioned_table WHERE partrelid = 'audit_logs'::regclass AND partdefid <> 0")
  [ "$default" = 0 ] && pass "no DEFAULT partition" || fail "a DEFAULT partition exists ($default)"

  rows=$(sql "SELECT count(*) FROM audit_logs")
  info "audit_logs rows: $rows; newest: $(sql "SELECT max(created_at) FROM audit_logs")"
  if [ -n "${EXPECTED_MIN_AUDIT_ROWS:-}" ]; then
    [ "$rows" -ge "$EXPECTED_MIN_AUDIT_ROWS" ] 2>/dev/null \
      && pass "no audit rows lost ($rows >= $EXPECTED_MIN_AUDIT_ROWS before the deploy)" \
      || fail "audit rows: $rows, but $EXPECTED_MIN_AUDIT_ROWS before the deploy"
  else
    skip "row-loss check (set EXPECTED_MIN_AUDIT_ROWS to the pre-deploy count)"
  fi

  pii=$(sql "SELECT count(*) FROM audit_logs WHERE action IN ('user.list_viewed', 'user.viewed') AND (coalesce(before_data::text, '') || coalesce(after_data::text, '')) LIKE '%@%'")
  [ "$pii" = 0 ] && pass "PII-read audit rows hold no email address" \
    || fail "$pii PII-read audit rows contain '@'"
  info "PII-read audit rows so far: $(sql "SELECT count(*) FROM audit_logs WHERE action IN ('user.list_viewed', 'user.viewed')")"
else
  fail "audit_logs is not partitioned (relkind: ${kind:-none}) - has the c3d5e7f9a1b2 migration run?"
fi
info "alembic revision: $(sql "SELECT version_num FROM alembic_version")"

echo
[ "$FAILED" = 0 ] && echo "VS-012 post-deploy check: ALL PASSED" || echo "VS-012 post-deploy check: FAILED"
exit "$FAILED"
