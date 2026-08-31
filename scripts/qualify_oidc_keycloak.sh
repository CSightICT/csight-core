#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$PROJECT_ROOT/infra/oidc/compose.oidc-qualification.yml"
OUTPUT_DIR="${OIDC_QUALIFICATION_OUTPUT_DIR:-$PROJECT_ROOT/local-data/oidc-qualification/latest}"
REPORT_PATH="$OUTPUT_DIR/qualification-report.json"

export OIDC_QUALIFICATION_DB_PASSWORD="$(openssl rand -hex 32)"
export OIDC_QUALIFICATION_ADMIN_USER="csight-qualification-admin"
export OIDC_QUALIFICATION_ADMIN_PASSWORD="$(openssl rand -hex 32)"
export OIDC_QUALIFICATION_USER_PASSWORD="$(openssl rand -hex 32)"
export OIDC_QUALIFICATION_SEED_ADMIN_PASSWORD="$(openssl rand -hex 32)"
export OIDC_QUALIFICATION_SEED_VIEWER_PASSWORD="$(openssl rand -hex 32)"

compose() {
    docker compose -f "$COMPOSE_FILE" "$@"
}

cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}

wait_for_url() {
    url=$1
    attempts=$2
    while [ "$attempts" -gt 0 ]; do
        if curl --fail --silent --show-error "$url" >/dev/null 2>&1; then
            return 0
        fi
        attempts=$((attempts - 1))
        sleep 1
    done
    return 1
}

trap cleanup EXIT INT TERM
cd "$PROJECT_ROOT"
umask 077
mkdir -p "$OUTPUT_DIR"
chmod 700 "$OUTPUT_DIR"
rm -f "$REPORT_PATH"

compose up --detach --build postgres keycloak
if ! wait_for_url \
    "http://localhost:18080/realms/csight-qualification/.well-known/openid-configuration" \
    60; then
    compose logs --tail=120 keycloak >&2
    exit 1
fi

compose build migrator
compose run --rm migrator
compose run --rm seed
compose up --detach api
if ! wait_for_url "http://127.0.0.1:18000/health/live" 30; then
    compose logs --tail=120 api >&2
    exit 1
fi

set +e
uv run python scripts/qualify_oidc_keycloak.py >"$REPORT_PATH"
qualification_status=$?
set -e
chmod 600 "$REPORT_PATH"
cat "$REPORT_PATH"
exit "$qualification_status"
