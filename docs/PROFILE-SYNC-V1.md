# Scoped profile synchronization v1

Source capability: `cross_server_profile_sync`. Independent registrations are
linked with bilateral consent; selected preferences then exchange automatically.
This extends [account links](PROFILE-LINKS-V1.md), preserving the old control-only
protocol and [read-only file tools](PROFILE-PACKETS-V1.md).

## User flow

On `/profile-sync/`, enter the other server and select **Отправлять** and
**Принимать**. All checkboxes start unchecked. Open the invitation in your
independently registered account on that server, check the exact pair and data
scopes, approve, then explicitly confirm the return link on the first server.
A fragment only prefills the form; landing never grants access.

Each confirmed data link shows current permissions, last successful exchange,
errors, pause/resume, manual synchronization (on the initiating server) and revoke.
Permissions can be reduced or restored only within the originally consented set.
Adding another kind requires a new bilateral invitation. Old control-only links
cannot acquire data access through a settings update.

The **Данные профиля** lists show original point URLs for favorites, point
subscriptions and own public posts, with pagination. A favorite may be removed
there. Open an original subscription/post to interact on its own server.
Paused/revoked grants stop subsequent exchange; they do not erase settings already
received. No production link is created by deploying this capability.

## Data and authority

Four independently authorized kinds:

- `color`: the six raw stat values; applied through `user_geometry`, with a local
  geometry invalidation event. It does not add account activity or influence.
- `favorites`: bookmarks keyed by canonical HTTPS origin and point ID. An
  own-origin bookmark is reflected in the normal local favorites API; external
  bookmarks remain links. Removing an imported bookmark records a deletion even
  if there was never a legacy `favorite_points` row.
- `subscriptions`: original point references only. Imported values never write
  `subscriptions`, support history or ballots; source-owned local subscription
  keys cannot be overwritten by an imported copy. Local support remains local.
- `own_points`: public original URI and original author ID, without body/title.
  Visibility is rechecked at exchange/list time; hiding/removing an original
  produces a tombstone. Imported references never create points, copy text,
  transfer authorship or overwrite the local source's own-original keys.

Passwords, sessions, recovery codes, roles, bans, point/author blocks, author
trust, ballots, support weights and influence have no wire fields. Author blocks
remain separate per server and site. This is not SSO or a database-user replica.
A reference records provenance claimed by the linked account, not a cryptographic
attestation by every third-party origin; it never grants ownership or authority.
No remote content is fetched to display a reference.

## Explicit private-data grant

The old `node06:link` token still only checks/revokes its grant. A new invitation
with nonempty scopes has `data:true`. It uses separate fixed `metadata-data` and
`token-data` endpoints. A data invitation/code is rejected by old metadata/token
endpoints, preventing a silent consent downgrade. Both account-pair confirmations
bind exact identities, origins, state, S256 PKCE and the displayed send/receive
sets. B stores reciprocal directions: A.send is B.receive.

The token-data response returns a **separate** opaque data token and echoes the
agreed scopes. A stores this outbound bearer credential; B stores only its hash.
Only the cookie-independent `/api/v1/profile-links/sync` accepts it. Neither token
is a browser login/session, and neither is returned in owner lists or exports.
The data bearer can exchange only selected preferences for its exact linked pair,
never read arbitrary users or call local social APIs. Lifetime remains 30 days.
Both accounts must remain active, grants unexpired and enabled.

Token storage needs protected database/backup access; credentials are not encrypted
at the application layer and no new operator secret/key setting is introduced.
Fixed-path transport retains verified public HTTPS443, complete DNS address
validation, pinned address/SNI, no redirects/proxies, shared verifier slots and
a hard subprocess deadline. Peer forms reject Origin/cookies/duplicate fields;
JSON rejects duplicate/unknown fields. Peer sync is bounded to 64 KiB form,
60 KiB JSON response, sixteen events per page, 180 requests/IP/minute. Other peer
operations retain 4 KiB form / 8 KiB response and their existing rate limits.
Keep request bodies out of proxy logs. Tokens never enter URLs/query parameters.

## Freshness, deletion and retries

Migration `0022_profile_preferences` adds per-account preference state, keyed
preferences and data-grant/polling columns. Each change has a version tuple:

`(clock, writer_origin, writer_user_id, event_id)`

`clock` is a hybrid logical millisecond tick multiplied by65536, at least the
previous accepted tick+1 for new local events. It is a decimal **string** on the
wire to avoid JavaScript integer precision loss, a BIGINT in PostgreSQL. Equal
clock values use the remaining fields for deterministic ordering. Equal complete
versions with different content are rejected. Accepted remote ticks advance the
local clock. A clock over five minutes ahead of local wall time is rejected
visibly; operators must correct clock skew rather than silently lose later edits.
This is deterministic last-writer-wins convergence, not causal multi-value history.

Native favorites/subscription-active/color transactions record events through
triggers using the trusted transaction-local management origin. Imported colors
suppress trigger restamping. First exchange baselines older native state without
replacing newer records. Revision repinning without an active-subscription change
does not restamp the preference.

Deletion is an explicit per-key tombstone. Missing items never imply deletion.
Tombstones are retained until the account is deleted; no age-based cleanup can
resurrect an old bookmark after a long outage. Sync has a10,000-record account
budget, including tombstones; exceeding it reports a limit, never truncates.
The normal native add-favorite limit remains64; merging independent bookmark
sets can exceed64, after which new native additions require removing items.
Legacy file export remains source-scoped and limited to128 references; it is not
a complete export of federated preferences and is not a synchronization grant.

A initiates a two-way exchange: push one A page, apply/return one B page. Stable
key cursors are durable on A and advance only after a validated response and
local commit. A cursor must acknowledge the last returned key; duplicate,
backwards and arbitrary skip cursors are rejected. Repeating a page after a lost
response is idempotent. Concurrent changes behind a cursor arrive on the next
full sweep; intermediate states may be coalesced, but latest keyed state remains.

A background worker checks at most four due links per turn. Incomplete sweeps
continue after2 seconds, complete sweeps repeat after60 seconds. Outages back off
from10 to900 seconds; preparation failures back off too so one broken account
cannot starve others. Database leases expire after the network deadline+30seconds;
restarts resume persisted cursors. Network calls hold no graph/user transaction
locks. Generation/lease/session checks prevent applying a response after local
pause, scope change or revoke. An in-flight page already accepted by the peer
cannot be recalled; pause/revoke does not retract previously received settings.

A polls; B does not get a reverse outbound token. If A is offline, B changes wait
until A returns. B may restrict/pause independently. Peer scope reductions filter
unapproved data before application. A revoked/disabled peer rejects the next
exchange; **Проверить связь** refreshes its displayed control status. Failed
outbound revocations retry in the worker; local revocation is immediate.
An entirely lost token response can leave an unreachable B grant until B revokes
it or it expires, with no client token available for recovery.

## API

- `POST /me/profile-links/invite`: existing origin plus optional `send`, `receive`.
- `GET /me/profile-links`: whitelisted current/allowed scopes, enabled/error/time;
  never credentials. Paths here are relative to `/api/v1`.
- `POST /me/profile-links/{id}/sync-settings`: `{enabled,send,receive}`;
  session+CSRF, only original consent subsets.
- `POST /me/profile-links/{id}/sync`: `{}`; one bounded page exchange, initiating
  account only; returns `{complete,sent,received}`. Background work continues.
- `POST /profile-links/sync`: peer-only form `{token,packet}`. Packet schema is
  `Message` in `profile_sync.py`; entries use strict `Entry` in
  `profile_preferences.py`. Token and exact pair/permission binding are mandatory.
- `GET /me/profile-sync/preferences?kind=...`: own active references,30 per page,
  `next_cursor` with `after_origin`,`after_point`. No private profile public API.
- `POST /me/profile-sync/favorite`: `{origin,point_id,active}`; own session+CSRF,
  no remote fetch or local point/reaction creation.

## Rollout and validation

Apply migration0022 through the existing reviewed deployment pipeline before
starting the new worker/application. No additional daemon, dependency, environment
secret or production registration is required. Back up before migrating. Downgrade
to0021 removes sync preferences/grants, retaining native users, social support,
color and legacy favorites; imported-only bookmarks/versions are lost. Revoke
links before downgrade if peers may remain enabled. A DB restore cannot retract
already shared data. Do not treat a source push as deployment or public acceptance.

`test_profile_sync.py` uses two independently migrated PostgreSQL schemas/apps:
explicit scope consent/downgrade protection, bilateral color/bookmark deletion,
source-owned reference boundaries, pagination, lost-response replay, worker,
scope reductions/pause/revoke, private token/session isolation, malformed fields,
future clocks, version ties/conflicts and interrupted-generation checks.
Existing pairing/transport/site-filter/social/migration tests remain mandatory.
Installed-wheel HTTPS browser acceptance covers unchecked scope selection,
invitation/cancel/no-write-fragment, external bookmark display/removal, mobile
layout and existing file export/comparison. Public two-server deployment is a
separate operator acceptance step; disposable tests read no production profiles.

Source validation checkpoint (25 October2026): full PostgreSQL backend366 passed;
final sync suite10 passed, including hidden-original removal, disabled/expired
peer denial and populated0022→0021→head roundtrip preserving native users/color/
favorites/support. Installed-wheel complete HTTPS browser acceptance passed;
mobile screenshot has no horizontal overflow. Backend Ruff/format, JavaScript
syntax, graph build61, clipboard/protocol and Git diff checks passed. No production
service, profile, link or database was changed.
Final pairing+sync regression26 passed after the expired-link status correction.
