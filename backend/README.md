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
built into `/setup/` (Russian) and `/setup/en/` (English). Static menu links use connection.json;
hosted pages use the configured management origin, never a parent login form.

Social geometry: migration `0012_social_geometry` adds private user coordinate
profiles and version-pinned blocks. See [geometry contract](../docs/SOCIAL-GEOMETRY-V1.md)
for finite T1 budgets, anonymous API/iframe batches, UI, freshness and rollback.
Use `/community/#my-color` for your color. A block swaps opposite components;
unsubscribe is neutral. Online migrations and disposable DB tests are required.

The management-host map can open `/editor/` in a same-origin modal. Only editor
HTML now permits SAMEORIGIN framing; account pages and the external embed host
remain isolated. External authenticated embedding is still not implemented.
Browser acceptance must follow pytest rather than run alongside it: both fixtures
rebuild the shared `dist/` directory.


Embedded creation uses anonymous `/compose/v1/{site_id}/` frames and top-level
`/editor/confirm/{site_id}/` review. Public bridge remains read-only. Apply0013
`compose_receipts` before enabling this application version: exact operation keys
are globally bound to actor/site/content for safe popup reload/account-change
retries. The configured application deploy performs the normal backup/migration
sequence; no new proxy/API exposure or third-party cookie is required. See
[embedded drafting contract](../docs/EMBEDDED-DRAFTS-V1.md).


Scoped reports/moderation: [contract](../docs/MODERATION-V1.md). Migration0016
adds roles, cases, unique reporters, reversible hides and audit. Later migrations
add bans and permanent cleanup as described below. The initial server admin is
an exact existing user ID granted
by the owner-run `python -m node06_service.moderation_admin --user-id …` command
inside the configured service environment; no handle is implicitly privileged.
Downgrading or running an old binary can expose hidden content: read the rollback
boundary before release. Neocities static files are outside server read control.

Public discovery: `/directory/`, public handle search and persisted T1 user /
confirmed current-version point rankings; scoped moderator user search includes
registration date/state. See [directory contract](../docs/DIRECTORY-V1.md).
No new migration or dependency; normal application/static deploy.

Scoped bans/quarantine: [contract](../docs/SCOPED-BANS-V1.md). Apply Alembic0017
before starting the app; `/ready` alone does not establish the schema revision.
No new configuration/dependency. No account disabling. Permanent cleanup is
implemented separately in0018.

Public reference collection: [POINT-CLIPBOARD-V1](../docs/POINT-CLIPBOARD-V1.md).
Local storage checks: `node scripts/check-point-clipboard.cjs` from repository root.


Permanent content cleanup: [contract and operator procedure](../docs/CONTENT-PURGE-V1.md).
Apply Alembic0018 before starting the updated service. Existing server hides
older than 30 days become eligible immediately; backup/review them before rollout.
Once a tombstone exists, downgrade below 0018 is refused. This source change does
not establish a production deployment.


Owner GitHub sources: [contract and limits](../docs/GIT-SOURCES-V1.md). Apply
Alembic0019 before starting this application. Owner-only registration/proof, private
preview/accept and opt-in polling live under «Мои сайты». Existing operator
sources retain their deployment authority. No new dependency, credential or timer.
Multilingual home presentation is implemented with complete Git/UI variants and
per-language link destinations: [HOME-BLOCKS-V1](../docs/HOME-BLOCKS-V1.md).
It adds no migration, graph locale partition or point identity change. Static and
hosted copies share the renderer/JS; existing wiki manifests need explicit
translations after the engine rollout.


Private profile export and comparison: [PROFILE-PACKETS-V1](../docs/PROFILE-PACKETS-V1.md).
The first-party navigation opens `/profile-sync/`. No migration or dependency is
added. This packet does not link servers, import settings or transfer influence;
network synchronization requires the separate consent protocol described below.

Bilateral account-link consent and revocation: [PROFILE-LINKS-V1](../docs/PROFILE-LINKS-V1.md),
migration `0020_profile_links`. The page remains `/profile-sync/`, with file tools
collapsed below the connection controls. The base control-only protocol is not profile exchange or SSO. Control-only opaque tokens in the DB require the same protected backup
handling as other application credentials; no new environment secret is needed.
Migration `0021_site_author_blocks` adds independent site-local personal author
filters, separate from server blocks/T1 and never exported/synchronized.
Both migrations must run before deploying this application through the operator
pipeline. Nothing in these source changes alone establishes production rollout.

Scoped automatic preference exchange: [PROFILE-SYNC-V1](../docs/PROFILE-SYNC-V1.md),
migration `0022_profile_preferences`. Explicit bilateral send/receive permissions
and separate data credentials enable color/bookmark merging and external
subscription/own-post references, with durable deletions/retries. Old control links
stay control-only; passwords, roles, bans, author blocks, trust and influence are
not replicated. The application starts its bounded sync worker automatically
when a database is configured. Deploy/migrate through the existing operator path;
source tests do not establish production installation or account linking.

Static-site subscription actions: [EMBED-SUBSCRIPTIONS-V1](../docs/EMBED-SUBSCRIPTIONS-V1.md),
migration `0023_embed_subscriptions`, capability `scoped_embed_subscriptions`.
A separate explicit15-minute grant permits point-subscription state/toggles only;
no global cookie, role, author trust or generic write authority reaches a parent.
The account page can revoke these grants. Partitioned cookie restoration is
optional; denied storage uses iframe memory and remaining-consent reconnection.
Approval recognizes the existing common server account even in detached tabs;
iframe-held PKCE completion does not require `window.opener`.
Apply the migration/server release before relying on the updated static controls.
General authenticated full-iframe operations remain outside this limited packet.
