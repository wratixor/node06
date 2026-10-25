# Permanent content cleanup

Implemented in source, 25 October 2026. Requires Alembic `0018_content_purge`.
This document describes application behavior, not a production deployment.

## Retention

Only uninterrupted **server** hiding starts the 30 × 24-hour retention period.
Site hiding, bans and quarantine do not start it. Repeated hiding preserves the
original start; restoration before cleanup cancels it. A later hide starts again.

The existing social worker checks one due point per pass (normally every 30 seconds),
under the shared transaction-level graph lock. It samples PostgreSQL's wall clock
**after** acquiring that lock. Restoration, publication and competing workers
serialize with it. A failed transaction rolls back the ledger and erasure together;
repeated passes skip already cleaned IDs. No ordinary GET performs cleanup.

## What remains

`point_tombstones` permanently records point ID, original hide start and purge time.
Point and revision IDs remain; the point is retired. All revision bodies, search
copies and declared links are cleared, including proposal candidate revisions.
Core publication bodies, point-owned proposal text and structured `static_body`
snapshots in subscriptions, blocks and other revisions/proposals are cleared.
A purged site entrance also loses display name, welcome text, home-page JSON and
theme; domain registration, owner and site ID remain.

Open proposals become stale. Closed proposal outcomes, revision hashes, receipt
IDs, moderation reports/audit and independently authored text remain. Cleanup does
not search and replace matching phrases in somebody else's post or private report.
Subscriptions to the removed point become inactive, invalidating the influence
snapshot through a new social event. No T1 budget formula changes.

## Public behavior and resurrection prevention

A direct public point read returns 200 with `deleted: true`, empty body and links,
and a fixed deletion notice. It reveals no private moderation reason. Existing
addresses can open this marker on the hosted map. Search, graph lists, feed,
profile lists, geometry and normal history exclude the removed content.
The marker offers no subscription/editor action toolbar.

Raw reads reject `POINT_PURGED` (410), even with moderation bypass enabled.
Restore, authoring, active social mutations, proposal votes, site settings and
old authoring receipts cannot republish a purged ID. Core synchronization skips
these IDs. Operator Git publication rejects a candidate containing one, including
check-only publication; remove that ID from the source manifest to publish other
roots. Ordinary Git retirement remains reversible for IDs that were never purged.
PostgreSQL triggers additionally prevent restoring revision/core text or switching
the retired point's revision pointer. These are application integrity guards, not
protection against an operator with privileged database access.

## Operator rollout and rollback

1. Back up the database under the existing backup policy. Inspect old server hides:
   records already older than 30 days become eligible on the first worker pass.
2. Stop the old application/worker, install the reviewed application, run
   `python -m alembic upgrade head` using its configured database, then start the
   updated service. Do not run old writers against this schema after cleanup.
3. Check `/api/v1/meta` for `content_tombstones`, service/worker errors and
   `moderation_audit` entries with action `purge`. This packet adds no new timer,
   dependency, credential or configuration setting.

Downgrade below 0018 is permitted only while the tombstone ledger is empty. Once
cleanup has occurred, migration downgrade refuses to remove its permanent guards.
Do not roll back to old application code that lacks these guards. Recovery from
an earlier database backup is a separate operator procedure and must preserve or
reapply later moderation decisions; it is not an automatic restore button.

Source Git repositories, independent static Neocities copies, backups, external
caches and other servers are outside this database cleanup. A disconnected static
copy may still contain its original Git roots. No claim of remote erasure is made.

## Validation

Run against a disposable `node06_test_*` PostgreSQL database with the project's
`postgresql+psycopg` driver:

```sh
NODE06_TEST_DATABASE_URL=... .venv/bin/pytest backend/tests/test_purge.py
NODE06_TEST_DATABASE_URL=... .venv/bin/pytest backend/tests
NODE06_TEST_DATABASE_URL=... .venv/bin/python scripts/check-hosted-browser.py
```

The focused tests cover the exact cutoff, restore/re-hide, site-only isolation,
all revisions and structured snapshots, receipt/Git/core resurrection guards,
transaction rollback and concurrent workers. Browser acceptance installs a wheel
and checks a real purged marker through hosted rendering and the read bridge.

Verified25 October: focused PostgreSQL cleanup tests8/8, online migrations and
empty-ledger downgrade/upgrade, populated-ledger downgrade refusal, installed-wheel
HTTPS Chromium (including the tombstone and anonymous bridge), and static51-root
navigation passed. The full DB-enabled run produced267 passes and4 existing SQLite
fixture failures (`clock_timestamp` absent); the failure was reproduced on main.
The test-only clock adapter fixes those fixtures: both affected modules passed8/8,
and the final no-DB suite passed118 with153 PostgreSQL-only tests skipped. Those
PostgreSQL tests were exercised in the DB-enabled run, not replaced by skips.
Backend Ruff/format, JS syntax, protocol/clipboard and Git diff checks passed.
