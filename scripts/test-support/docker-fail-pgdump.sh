#!/usr/bin/env sh
set -eu
case " $* " in
  *" exec -T postgres pg_dump "*)
    echo "injected pg_dump failure" >&2
    exit 97
    ;;
esac
exec docker "$@"
