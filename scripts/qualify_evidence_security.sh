#!/bin/sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
CORE_COMPOSE="$PROJECT_ROOT/infra/compose.core.yml"
SECURITY_COMPOSE="$PROJECT_ROOT/infra/evidence/compose.evidence-security.yml"
PROJECT_NAME="csight-evidence-qualification"
OUTPUT_DIR="${EVIDENCE_QUALIFICATION_OUTPUT_DIR:-$PROJECT_ROOT/local-data/evidence-security-qualification/latest}"
HEALTHY_REPORT="$OUTPUT_DIR/healthy-report.json"
OUTAGE_REPORT="$OUTPUT_DIR/outage-report.json"

export ENVIRONMENT="test"
export CSIGHT_IMAGE_TAG="evidence-qualification"
export API_PORT="18100"
export POSTGRES_PORT="15434"
export RABBITMQ_PORT="15674"
export RABBITMQ_MANAGEMENT_PORT="19674"
export MINIO_PORT="19100"
export MINIO_CONSOLE_PORT="19101"
export MAX_UPLOAD_BYTES="1048576"
export WEB_MAX_UPLOAD_BODY="4m"
export POSTGRES_PASSWORD="$(openssl rand -hex 32)"
export RABBITMQ_DEFAULT_PASS="$(openssl rand -hex 32)"
export MINIO_ACCESS_KEY="csight-evidence-qualification"
export MINIO_SECRET_KEY="$(openssl rand -hex 32)"
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export DEVELOPMENT_SEED_ENABLED="true"
export DEVELOPMENT_SEED_ADMIN_PASSWORD="$(openssl rand -hex 24)"
export DEVELOPMENT_SEED_REVIEWER_PASSWORD="$(openssl rand -hex 24)"
export DEVELOPMENT_SEED_QUALITY_VIEWER_PASSWORD="$(openssl rand -hex 24)"
export EVIDENCE_QUALIFICATION_ADMIN_PASSWORD="$DEVELOPMENT_SEED_ADMIN_PASSWORD"

compose() {
    docker compose \
        --project-name "$PROJECT_NAME" \
        --file "$CORE_COMPOSE" \
        --file "$SECURITY_COMPOSE" \
        "$@"
}

cleanup() {
    compose down --volumes --remove-orphans >/dev/null 2>&1 || true
}

wait_for_api() {
    attempts=60
    while [ "$attempts" -gt 0 ]; do
        if curl --fail --silent --show-error \
            "http://127.0.0.1:${API_PORT}/health/live" >/dev/null 2>&1; then
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
rm -f "$HEALTHY_REPORT" "$OUTAGE_REPORT"

compose up --detach postgres rabbitmq minio clamav
compose build api migrator
compose run --rm migrator
compose run --rm \
    -e DEVELOPMENT_SEED_ENABLED \
    -e DEVELOPMENT_SEED_ADMIN_PASSWORD \
    -e DEVELOPMENT_SEED_REVIEWER_PASSWORD \
    -e DEVELOPMENT_SEED_QUALITY_VIEWER_PASSWORD \
    api uv run python -m app.bootstrap.seed --env-file /dev/null
compose up --detach api
if ! wait_for_api; then
    compose logs --tail=160 api clamav >&2
    exit 1
fi

uv run python scripts/qualify_evidence_security.py \
    --phase healthy \
    --api-base "http://127.0.0.1:${API_PORT}" >"$HEALTHY_REPORT"
chmod 600 "$HEALTHY_REPORT"
cat "$HEALTHY_REPORT"

compose stop clamav
uv run python scripts/qualify_evidence_security.py \
    --phase outage \
    --api-base "http://127.0.0.1:${API_PORT}" >"$OUTAGE_REPORT"
chmod 600 "$OUTAGE_REPORT"
cat "$OUTAGE_REPORT"
