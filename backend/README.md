# NODE06 backend bootstrap

This directory starts P01 only: configuration, a PostgreSQL migration boundary
and liveness/readiness metadata. It contains no accounts, sites, points, embeds,
or production deployment configuration yet.

Create an isolated environment and install the backend from the repository root:

```bash
python3 -m venv .venv
.venv/bin/pip install -e '.[dev]'
cp backend/.env.example .env
.venv/bin/alembic upgrade head
.venv/bin/node06-service
```

Set `NODE06_DATABASE_URL` before applying migrations. The development example is
deliberately non-working until the developer creates a disposable local database;
no database name, password or host is embedded in source. `GET /api/v1/health`
does not use PostgreSQL. `GET /api/v1/ready` returns `503` until PostgreSQL is
configured and reachable.

Dependency versions were resolved from PyPI on 13 September 2026. Refreshing them
is a deliberate maintenance change and must be tested, rather than an implicit
production upgrade.
