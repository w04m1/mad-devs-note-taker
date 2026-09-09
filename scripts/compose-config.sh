#!/usr/bin/env sh
set -eu
cd "$(dirname "$0")/.."
docker compose config --quiet
echo "compose configuration is valid"
