# Notetaker

A client-server note and reminder application. See [`PLAN.md`](PLAN.md) for the implementation plan and [`customer-requirements.md`](customer-requirements.md) for the source constraints.

## Local development

Prerequisites: Docker Engine 27+, Docker Compose v2.24+, 4 GB free memory, and `curl`. Application dependency manifests are supplied by the backend and frontend implementation workstreams.

```sh
docker compose up --build --wait
```

Open <http://localhost:5173>. Mailpit is at <http://localhost:8025>. Local defaults need no `.env`; copy [`.env.example`](.env.example) to override them.

Useful checks:

```sh
./scripts/compose-config.sh
./scripts/smoke.sh
./scripts/test.sh
```

The stack has seven long-lived services and a one-shot migration. PostgreSQL and Redis data survive `docker compose down`. Do not use `docker compose down --volumes` unless you intend to erase local data.

See [`docs/infrastructure.md`](docs/infrastructure.md) for setup, integration assumptions, migrations, logs, LAN testing, backup/restore, and troubleshooting. Current product scope and implementation status are tracked by the plan and later feature workstreams.
