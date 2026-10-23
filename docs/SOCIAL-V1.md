# Social v1 — source contract

Implemented 23 October 2026. Source/test completion is not a production deployment claim.
Migration `0010_social_versions` depends on `0009_point_authoring`.

## Actions and authority

Semantic links, subscriptions and explicit proposal ballots are separate. A
subscription supports one immutable revision/digest. Static roots have real body
snapshots and null revision IDs, never synthetic revision IDs. Normal changes
keep old support on the old text. Every Git root is protected: an accepted source
update automatically transfers active support, records each previous pin and
publishes a public Git changelog. Removed sources publish retirement once; they
do not manufacture a new supported text.

An active account can propose one change in a rolling 24 hours instance-wide.
Failed validation/replay does not consume another slot. One open proposal per
point is enforced by a partial unique index. Even the author/site owner cannot
directly replace subscribed text; theme/domain management remains owner-managed.
An unsubscribed, non-Git point remains directly editable by its author.

A proposal pins base and reference targets, stores an immutable candidate and
freezes a 72h deadline. Opening it casts no vote and does not subscribe the author.
Voting atomically enrolls/switches subscription and replaces the actor's single
old/new ballot. Unsubscribing withdraws an open ballot. A regular subscription
cannot silently change a ballot. Stale base/targets prevent adoption.

At deadline, adopt iff explicit new influence exceeds explicit old influence.
Silent subscribers count on neither side. Ties and zero cast influence retain
the base. Immediately adopt when explicit new ballots cover all positive current
subscribed influence; silent positive influence prevents only early completion.
Adoption is atomic, preserves original authorship, updates reciprocal link claims
without deleting other provenance, and publishes candidate history only then.

## Approved T1 numerical contract

The owner explicitly approved T1 for the first version with total-conservation
validation. Active means an enabled local account, not recent login activity.
Each contributes one base unit; sites/links/imports do not create units.
For each source user, T distributes equally among self and explicitly trusted
active users. Solve `w' = 0.5 * 1 + 0.5 * transpose(T) * w` in sorted ID order.
Maximum 128 iterations, L1 residual <= `1e-12 * max(1,N)`; check total error <=
`1e-9 * max(1,N)`. No headcount fallback on calculation/capacity failure.

Version `t1-v1-d0.5-q12`, scale `10^12`: normalize converged half weights and
quantize by largest remainder (fractional part, then stable user ID). Twice that
integer half is effective influence; the two half budgets are exactly equal.
Split the point half across distinct active public subscriptions, integer
quotient/remainder by point ID. Pending/old pins reserve their share instead of
duplicating it. No subscriptions means idle point budget. Exactly:

- `sum(effective weights) = N * scale`
- `people budget = N * scale / 2`
- `confirmed point mass + held pending + idle = N * scale / 2`

Ballots use that user's allocated share for THIS point, never full user weight
again. Both sides use the same transactionally computed snapshot. Decimal strings
cross the API; browsers do not supply weights. Adoption stores snapshot ID/model
and exact totals. Positive support only; signed opposition and semantic geometry
are not implemented by this packet.

Input digest includes event cutoff, enabled users, trust and version pins. Keep
last good published snapshot; reads explicitly say pending when social input has
changed. A fresh authoritative snapshot is recomputed at a binding decision.
Current alpha caps: 10,000 active users, 100,000 trust edges, 100,000 subscriptions.
These are safety guards, not tested production capacity promises. Snapshot/history
retention, Sybil defenses and performance at these ceilings remain operational work.

## Transactions and worker

Every graph writer takes the same PostgreSQL advisory transaction lock before
actor/point/source locks. This deliberately serializes graph mutations for alpha;
authentication remains separate. Active-user locks protect snapshot eligibility.
Finalization, version pointer, link claims, audit and outcome share a transaction.
Idempotency-Key fingerprints actor + action + payload; conflicting reuse is 409.

Configured database_url starts an application lifespan worker automatically.
Every 30 seconds it baselines core roots and synchronizes changed static publications, checks
up to 20 due proposals and round-robin other open proposals, publishes a snapshot,
and delivers a bounded outbox batch (20 events, 50 recipients each). Multiple
processes serialize through the graph lock. Durable cursor/unique inbox keys make
restarts/retries safe. Subscription intervals select event-time recipients, so
unsubscribing later does not erase an already owed notice. No email is sent.
Worker status is reported in meta. SQL/capacity failures leave durable work for
retry, log only error class and never parameters/DSNs. No new privileged timer or
operator deploy-tool installation is needed. UI feed refresh is explicit.

## HTTP and UI

First-party `/community/?p=POINT` provides safe old/new plain-text comparison,
explicit support/voting, trust search, own subscriptions, private inbox and public
Git news. `/account/` supplies login; users need not own a site. Static and full
embed copies link out to trusted management. No credentials go to the parent.

All writes require same-origin authenticated session, CSRF and Idempotency-Key;
JSON body limit is 64 KiB, actor/IP rate limits apply. Exact payloads live in
`social_api.py`; public point existence is checked before exposure.

- POST `/api/v1/points/{id}/subscription`: revision_id, content_digest, active
- POST `/api/v1/points/{id}/proposals`: authoring content/reference pins plus expected_revision_id, expected_digest
- POST `/api/v1/proposals/{id}/vote`: choice old/new
- POST `/api/v1/people/{id}/trust`: active
- POST `/api/v1/me/inbox/{event_seq}/read`: empty object
- GET `/api/v1/points/{id}/social`, `/proposals/{id}`, `/news`, `/people?q=...`
- Private GET `/api/v1/me/social`, `/me/subscriptions/{id}`, `/me/influence`, `/me/inbox`

Published proposal text is public; private subscriptions, choices and inbox are
not a public subscriber directory. Public iframe/bridge stay read-only.

## Deployment, validation and remaining work

Back up application/database before online `alembic upgrade head`; 0008 already
requires online Unicode backfill. Build dist and install wheel from the same
accepted revision, restart, check ready/meta worker, registration, community and
real parent/embed browsing. The existing deploy pipeline follows accepted main;
a feature push does not publish this packet. A schema downgrade destroys social
history: application rollback with preserved tables/backup is safer than claiming
a lossless downgrade after real usage.

Disposable PostgreSQL tests cover exact ballots, silent subscribers, weighted
minority beating account majority, tie, daily lock, author bypass, private inbox,
Git transfer/replay, static snapshots, competing votes and proposals. Pure T1
tests cover conservation, isolated/cyclic/star/asymmetric graphs and deterministic
rounding. Installed-wheel HTTPS Chrome test covers the real community form,
escaped comparison, immediate adoption, background notification and protected
roots alongside account/sites/bridge flows. No real production account/DB used.

Still future: signed reactions/geometry, federation/profile sync, scoped embed
writes, quotas/billing, adaptive voting duration, self-service imports, snapshot
retention and large-scale performance qualification. Registration has no invented
proof-of-personhood: account farming remains a product limitation of base-one T1.

## Field summaries — source packet, 23 October 2026

The field text panel and shared public search detail now show support/version
state without leaving the map: current-version influence, influence held on other
versions, open proposal and explicit weighted old/new totals. A contextual link
opens first-party comparison/subscription/voting in a separate tab. Geometry,
sphere radii and T1/voting rules are unchanged. No authenticated bridge writes.

`GET /api/v1/points/{id}/social-summary` and bridge method `point.social` share
`node06-point-social/1`: current revision/digest, protection, influence
(available/pending/current/held/subscribed/snapshot_id/model), and at most one
open proposal (id, ISO close time, nullable old/new tally). It omits proposal
bodies, author/subscriber identities, individual ballots and account state.
Pending/unpublished values are null, never fake zero. An actual fresh zero is
represented as decimal string `"0"`. No headcounts substitute for influence.

T1 snapshots now persist per-point current/held/subscribed integer allocations
with their public current-version pins. A projection-format marker in the input
identity forces publication after upgrade even when social inputs are unchanged.
This is derived JSON, requiring no new migration or mass-formula change. Old
projection rows remain history; until the worker publishes the new format,
summary reads are explicitly pending. Active-user set, event cutoff and source
pin changes invalidate the fresh label. Read-side proposal tallies are checked
again against the event cutoff after collecting ballots. Final decisions still
use the existing graph transaction and a newly computed authoritative snapshot.

Graph payloads include revision/digest pins for built core, site, Git and authored
points. The UI compares the displayed pin with the server summary; an outdated
local text is marked changed and never given the current text's influence label.
It keeps the text visible and offers review on the trusted server. Slow responses
for detached/replaced point panels cannot overwrite the current point.

Personal active subscription/version and explicit own ballot are read only via
same-origin `/me/subscriptions/{id}` on the management host, with the existing
cookie. A 401 says sign in; read failure is not presented as no subscription.
Static parents/full frames show the public aggregate and a trusted management
link, never the account cookie/CSRF or a claim that the visitor is unsubscribed.
Refresh is manual or on returning window focus; there is no continual polling.
The renderer and picker share one public transport/iframe. Registered site,
parent/source/channel checks and method/parameter/size limits remain in force.

Compatibility: method addition preserves node06-embed/1. Older servers can still
serve existing picker methods; missing social support produces an update/
unavailable message without blocking text. Core builder pins use the same
canonical digest as public reads. Updated frontend/dist and backend should ship
from the same reviewed revision through normal deployment. No extra service,
privileged timer, or migration is introduced by this packet.
