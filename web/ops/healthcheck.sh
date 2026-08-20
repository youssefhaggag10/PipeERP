#!/bin/sh
set -eu

base_url=${PIPEERP_BASE_URL:?PIPEERP_BASE_URL is required}
health_path=${PIPEERP_HEALTH_PATH:-/api/v1/health/ready}
webhook_file=${ALERT_WEBHOOK_URL_FILE:-}

case "$base_url" in
  https://*) ;;
  http://*) [ "${ALLOW_HTTP_HEALTHCHECK:-}" = "YES" ] || {
    echo "فحص HTTP غير مسموح دون ALLOW_HTTP_HEALTHCHECK=YES" >&2
    exit 1
  } ;;
  *) echo "PIPEERP_BASE_URL غير صالح" >&2; exit 1 ;;
esac

if curl --fail --silent --show-error \
  --connect-timeout 5 --max-time 10 \
  "$base_url$health_path" >/dev/null; then
  echo "PipeERP readiness is healthy"
  exit 0
fi

echo "PipeERP readiness failed" >&2
if [ -n "$webhook_file" ] && [ -r "$webhook_file" ]; then
  webhook_url=$(sed -e 's/[[:space:]]*$//' "$webhook_file")
  curl --fail --silent --show-error --connect-timeout 5 --max-time 10 \
    -H 'Content-Type: application/json' \
    --data '{"text":"PipeERP production readiness check failed"}' \
    "$webhook_url" >/dev/null || true
fi
exit 1
