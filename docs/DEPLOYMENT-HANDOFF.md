# NODE06 backend deployment handoff

Status: deployment contract only. No production deployment was performed from this repository.

The repository already contains a GitHub Actions workflow for the static Neocities build. It does
**not** deploy the backend. The backend deployment should be integrated with the operator's existing
server/deployment repository instead of inventing a second production path here.

## Runtime contract

The backend currently expects:

- Python `>=3.12,<3.15`;
- PostgreSQL (the migrations use PostgreSQL-specific partial indexes/JSON literals);
- `NODE06_DATABASE_URL` as a SQLAlchemy `postgresql+psycopg://...` URL;
- optional `NODE06_ENVIRONMENT`, `NODE06_HOST`, `NODE06_PORT`, `NODE06_BUILD_REVISION`;
- migrations applied with `alembic upgrade head` before the service revision becomes live;
- the `node06-service` console entry point (Uvicorn) behind the operator's HTTPS reverse proxy.

Health endpoints:

- `GET /api/v1/health` is liveness and deliberately does not touch PostgreSQL;
- `GET /api/v1/ready` is readiness and returns `503` until PostgreSQL is configured/reachable.

The service implements first-party account/session/recovery routes and owner site
management. Set the exact HTTPS `NODE06_MANAGEMENT_ORIGIN` and reviewed proxy
trust/timeouts before enabling writes. See [AUTH-V1](AUTH-V1.md) and
[SITE-MANAGEMENT-V1](SITE-MANAGEMENT-V1.md) for cookies, CSRF, budgets and bodies.
Migration head is `0004_verifier_leases`. The proof verifier uses spawned child
processes and PostgreSQL admission leases; allow child processes and use consistent
slot/deadline configuration across instances sharing the database. Confirm actual
host memory/process limits before opening registration/claims. Site management UI,
embed authorization and production acceptance remain unfinished.

## Safe deployment order

For an existing operator pipeline the intended order is:

1. build/install the exact repository revision;
2. supply secrets/configuration from the deployment environment, never Git;
3. apply Alembic migrations to PostgreSQL;
4. start/restart the service;
5. require `/api/v1/ready` to succeed before routing normal traffic;
6. retain the previous application revision and database backup/restore procedure for rollback.

Exact filesystem paths, systemd unit names, Nginx locations, database names and credentials belong to
the deployment repository/environment and are intentionally not guessed here.

## GitHub vs existing Gitea path

The current `.github/workflows/deploy.yml` validates the backend but only deploys `dist/` to
Neocities. For backend delivery from GitHub, prefer adapting the existing Gitea deployment mechanism
rather than adding a parallel SSH/systemd workflow blindly. The useful handoff artifact is therefore
the existing deploy repository/configuration (with secrets removed). Once supplied, map this runtime
contract onto its established build, release, migration, health-check and rollback steps.
