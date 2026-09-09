# Playwright E2E

Run the six full-stack scenarios from the repository root:

```sh
./tests/e2e/run.sh
```

The harness uses isolated Compose project `notetaker-e2e`, frontend port `15173`, Mailpit port `18025`, and removes its volumes after the run. Set `E2E_KEEP_STACK=1` to inspect failures. Pass Playwright arguments after the script name, for example `./tests/e2e/run.sh --grep "concurrent"`.

Failure traces, screenshots, videos, HTML report, and `artifacts/compose.log` are under `tests/e2e/artifacts/`. Open a trace with `corepack pnpm --dir tests/e2e exec playwright show-trace <trace.zip>`.

Data is created through real HTTP APIs. Each test starts with a PostgreSQL reset through `docker compose exec`; no reset or clock endpoint is exposed by the application. Redis duplicate-event injection and PostgreSQL delivery-state inspection also run inside the isolated Compose project. Key scenario actions remain browser UI actions.
