# NODE06 backend bootstrap

This directory contains P01 plus the first P02 site-registry slice: configuration,
PostgreSQL migrations, liveness/readiness metadata, public active-site read, and an
internal verified-origin lifecycle for site points. Public mutation routes are
intentionally deferred until P03 authentication rather than exposing a temporary
unauthenticated management API. Imports, reactions, trust and production deployment
configuration are not implemented yet.

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

## P02 site registry slice

Migration `0002_site_registry` introduces the minimum shared-graph primitives needed
for sites: users as ownership principals, points/revisions, sites/members/claims,
canonical undirected edges with provenance claims, and an event log. `all-sites` is
bootstrapped as a temporary DB projection until the general Git root importer (P04)
owns core-root projection.

Origin proof uses exactly `/node06-verification.txt`, HTTPS/443 only, a 30-minute
nonce challenge, max 8 KiB and a pinned public DNS address with TLS hostname
verification. Redirects and private/reserved/link-local/loopback targets are rejected.
The attempt counter commits before the outbound fetch so a bad proof cannot roll back
its own attempt.

`GET /api/v1/sites/{site_id}` is public for active sites. Claim creation/verification
remain service methods until authenticated P03 management routes are available.

See `docs/DEPLOYMENT-HANDOFF.md` before wiring this service into an operator pipeline.
