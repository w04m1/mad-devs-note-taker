#!/usr/bin/env sh
set -eu
cd /app
uv run --frozen python scripts/require_schema_head.py
exec "$@"
