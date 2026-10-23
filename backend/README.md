# NODE06 backend bootstrap

This directory contains P01, the P02 site registry, P03a shared account sessions
and P03b authenticated site management. It exposes account routes and the
first-party `/account/` page, health/meta, public active-site read and owner-only
create/list/manage/renew/verify/settings routes. `/sites/` is the first-party owner UI.
Operator Git publication, authoring and social v1 are implemented in source;
authenticated embeds, signed reactions and federation remain future work.

Account setup, HTTPS/cookie/CSRF boundary, recovery and configurable limits:
[docs/AUTH-V1.md](../docs/AUTH-V1.md). Set `NODE06_MANAGEMENT_ORIGIN` to the exact
HTTPS origin before using account writes. No email or SMS service is needed.
Implemented site payloads, limits, security and remaining work:
[docs/SITE-MANAGEMENT-V1.md](../docs/SITE-MANAGEMENT-V1.md).
Hosted game/lore entrance, shared public projection, read-only iframe, two-origin
setup and packaging: [HOSTED-WIKI-V1.md](../docs/HOSTED-WIKI-V1.md). The generated
frontend must be built before starting with `NODE06_HOSTED_DIST` configured.
Small iframe API bridge and copy-to-your-site SDK:
[PUBLIC-BRIDGE-V1.md](../docs/PUBLIC-BRIDGE-V1.md). Public reads only; no global
credentials or authenticated writes are passed to a third-party parent.

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

`GET /api/v1/sites/{site_id}` is public for active sites. Authenticated owner
management is now exposed over HTTP as documented in SITE-MANAGEMENT-V1.

Verification locks and checks the owner/site/claim before and after network I/O;
expiry is checked again after the fetch. Inactive sites and disabled owners cannot
be reactivated by replaying a proof. An existing origin is never automatically
transferred to a new claimant, even after expiry or deactivation. Pending claim
renewal and settings are implemented; release/transfer are not exposed.

### Validation

Run `.venv/bin/pytest`, `.venv/bin/ruff check backend` and
`.venv/bin/ruff format --check backend` from the repository root. Transport tests
require the `openssl` executable; they generate temporary certificates and use a
local HTTPS server with controlled DNS/dialing. They cover certificate hostname
validation, redirects, body limits and rejection of mixed public/private DNS.
They are not a real-Neocities deployment check.

For full integration coverage, provision an empty, disposable **UTF-8** PostgreSQL
database whose name starts with `node06_test_`, then set `NODE06_TEST_DATABASE_URL`
to its SQLAlchemy `postgresql+psycopg://...` URL before running pytest. Do not point
this variable at an application database. Each test creates its own random schema,
runs the actual Alembic upgrades through psycopg, and drops only that schema in
cleanup. Tests cover upgrades through `0004`, downgrade/re-upgrade,
duplicate-origin races, concurrent verification/replay, shared directory edges,
failed-proof attempts and owner/state/origin/challenge/expiry changes during fetch.
Without this variable PostgreSQL tests are explicitly skipped. GitHub Actions now
supplies its own disposable PostgreSQL 18 service so those tests are mandatory there.

A spawned proof worker adds a total DNS/TLS/body deadline, shared PostgreSQL
admission slots, durable account/IP rate limits and per-challenge attempt limits.
Tests also cover real child-process timeout/cleanup, slot races/expiry, owner/CSRF
boundaries, session revocation/challenge renewal during I/O, immutable welcome
history and concurrent settings edits. No migration has been applied in production.

See `docs/DEPLOYMENT-HANDOFF.md` before wiring this service into an operator pipeline.

## P04a root preflight

Read-only local Git snapshot validation: [ROOT-PREFLIGHT-V1](../docs/ROOT-PREFLIGHT-V1.md).
Run `python -m node06_service.root_preflight --schema` or supply repo, immutable
commit and expected site ID. No GitHub fetch, source proof verification, database
writes, server import routes or migrations are added by this slice.

Operator content publication and migration 0005: [deployment contract](../docs/OPERATOR-CONTENT-DEPLOY.md).

Per-site home blocks, owner editor and migration 0006: [HOME-BLOCKS-V1](../docs/HOME-BLOCKS-V1.md).

Public current-point reads, bounded full-body prefix search and migration 0008:
[PUBLIC-POINTS-V1](../docs/PUBLIC-POINTS-V1.md). Online Alembic upgrade is required
for its Unicode backfill; generated offline SQL deliberately fails at this step.

Point authoring and editor: [contract](../docs/POINT-AUTHORING-V1.md), migration
`0009_point_authoring`. Links are not support; proposal voting is a later packet.

Social v1: [SOCIAL-V1](../docs/SOCIAL-V1.md), migration `0010_social_versions`.
A configured database starts the bounded background worker in the application;
no separate root service/timer is required. Subscriptions, explicit revision
ballots, trust, private inbox and Git source changelog are implemented in source.
Apply online migrations and restart through the operator pipeline after review.
Connection/deployment modes for site owners: [SELF-HOSTING](../docs/SELF-HOSTING.md),
built into the public `/setup/` page. Static menu links use connection.json;
hosted pages use the configured management origin, never a parent login form.
