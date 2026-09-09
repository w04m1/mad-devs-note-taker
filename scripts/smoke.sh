#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."

cleanup_on_failure() {
  status=$?
  if [ "$status" -ne 0 ]; then
    docker compose ps || true
    docker compose logs --no-color --tail=150 || true
  fi
  exit "$status"
}
trap cleanup_on_failure EXIT INT TERM

docker compose up --build --wait --wait-timeout "${COMPOSE_WAIT_TIMEOUT:-180}"

curl --fail --silent --show-error --retry 5 --retry-connrefused   "http://${FRONTEND_BIND_ADDRESS:-127.0.0.1}:${FRONTEND_PORT:-5173}/" >/dev/null
curl --fail --silent --show-error --retry 5 --retry-connrefused   "http://${FRONTEND_BIND_ADDRESS:-127.0.0.1}:${FRONTEND_PORT:-5173}/api/v1/health/ready" >/dev/null
curl --fail --silent --show-error --retry 5 --retry-connrefused   "http://${MAILPIT_BIND_ADDRESS:-127.0.0.1}:${MAILPIT_UI_PORT:-8025}/api/v1/info" >/dev/null

running="$(docker compose ps --services --status running | sort)"
expected="$(printf '%s\n' backend beat frontend mailpit postgres redis worker | sort)"
[ "$running" = "$expected" ] || {
  echo "unexpected long-lived service set" >&2
  echo "running:" >&2
  echo "$running" >&2
  exit 1
}
[ "$(docker compose ps --all --services --filter status=exited | grep -c '^migrate$' || true)" -eq 1 ]

echo "smoke check passed: seven services running; migration completed"
trap - EXIT INT TERM
