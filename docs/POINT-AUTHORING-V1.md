# First-party point authoring v1

Source implementation, 23 October 2026; deployment is a separate state. This
slice is P05c, not a completed social layer. Public reads/bridge reuse the same
published content; writes happen only on the configured management origin.

## User workflow

Open `/editor/` (also linked from Account and the hosted header), sign in via
`/account/`, write text and choose its language. Language describes this point,
not a localized site. No site registration is required. Select words and use
**Связать выделенные слова / добавить связь** to search current public points.
Selection inserts `[words](md://point/id)` and pins that target's revision/digest.
Without a selection it adds a declared graph connection without changing prose.
Ordinary words stay ordinary words. Links never create endorsements.

Choose 1–16 distinct existing public targets, then Publish. The editor lists the
user's points and allows their author to reopen and edit. There is a readable
published version history. Network/conflict failures retain the editor's current
text in memory; there is no promise of disk draft recovery after closing/reloading.
Navigation warns about unsaved work. A lost write response retries its original
idempotency key; content stays read-only until that uncertain operation resolves,
so editing the payload cannot accidentally create a second point. History failure after success does not misreport publication.

The full iframe and small bridge remain read-only. Open the trusted Account/editor
in a first-party tab; session cookies/CSRF never go to a parent site's script.
Static Neocities point files remain the repository projection. Search can open
shared authored points in the hosted wiki; it does not rewrite local static files.

## HTTP contract

All writes require the existing active session, exact management Origin and
`X-CSRF-Token`, plus `Idempotency-Key` (8–80 ASCII alphanumerics, `-` or `_`).
No arbitrary query arguments; no public proxy/CORS expansion.

- `POST /api/v1/points`: body `{body, lang, links}`; returns 201
  `{id: "p_<uuid32>", revision_id: "v_<uuid32>", changed: true}`.
- `PATCH /api/v1/points/{id}`: same content plus `expected_revision_id`;
  returns the committed revision. Only the original author of an explicitly
  published user point can edit. Site/Git/system points use their existing paths.
- `GET /api/v1/me/points?after=<id>&limit=20`: authenticated own active points,
  ascending ASCII IDs, max 30, `{items, next_cursor}`.
- `GET /api/v1/points/{id}/revisions?before=<revision>&limit=10`: public history
  **only for explicitly published user points**, max 20. Cursor resolves a real
  revision of that point, using its `(created_at, id)` pair. Not a global event
  cursor or guarantee of global commit ordering. No site draft/history exposure.

`body`: nonblank, max 8192 characters and 32 KiB. `lang`: max 35 ASCII BCP47-like
characters (or `und`); this is a bounded label, not exhaustive language validation.
`links`: 1–16 unique `{id, revision_id, content_digest}` objects. A target must be
currently public and the supplied real revision ID (or null for static core) and
64-character digest must match current content. Inline `md://point/` references
must be declared in links; fenced and inline code are ignored. `md://local/`
links are not accepted for user content. HTML is escaped by the existing renderer.
The actual HTTP body is capped at 64 KiB before JSON parsing. Writes are durably
rate-limited to 120 per actor/hour and 240 per client IP/hour, including retries;
these are transport budgets, not the proposed one-proposal-per-day social rule.

Useful errors: `POINT_EDIT_FORBIDDEN` 403; `POINT_REVISION_CHANGED`,
`TARGET_REVISION_CHANGED`, `TARGET_NOT_PUBLIC`, `IDEMPOTENCY_CONFLICT` 409;
`UNDECLARED_POINT_LINK`, `DUPLICATE_POINT_LINK`, `SELF_LINK`, `INVALID_POINT_BODY`,
`IDEMPOTENCY_KEY_REQUIRED` 422; normal auth/CSRF/rate-limit codes apply.
To refresh a stale citation, explicitly remove and reselect its target. The server
never silently updates the author's citation to a changed meaning.

## Storage and concurrency

Online migration `0009_point_authoring` adds explicit `authored_points` publication
and language, immutable `authored_revisions` citation metadata/language, and
actor-scoped `point_operations` receipts. Existing `points.author_user_id` remains
the ownership source. Legacy bare `origin=user` rows are still not public.
No old point, site, root or account data is reclassified on migration.

Within one transaction, authorization locks/rechecks the active user/session,
receipts serialize on that actor, and all existing source/target points are locked
in sorted ID order. Current-target reads use that same connection after the locks;
source publishers also lock their points before replacing current revisions.
Authoring takes no target-owner or site locks. Source visibility may subsequently
change: historical references do not confer a right to keep a revoked site public.

A successful operation inserts immutable content/citation revisions, changes the
current pointer/language, replaces only `authored-point` edge claims belonging to
that point and emits one `point-created`/`point-edited` event. Other provenance
claims survive. Canonical graph edges are reciprocal; links retain their authored
direction in `declared_links`. An exact no-op writes only a replay receipt; no new
revision/event/activity timestamp. A replay returns its original committed result,
which may no longer be the point's latest revision. No vote/notification is implied
by these generic events. Sequence allocation is not a commit-order cursor.

Static core has no DB revision history: null stays null. The citation stores the
exact static text, digest and build source, not a fabricated persisted revision.
DB citations reference their immutable revision. Public history returns citation
identity/digest/source but omits stored static text to bound response size; these
snapshots are not yet a public historic-core browsing API.

Hosted graph adds published user points and reciprocal claimed edges, with
explicit capacity failure (`GRAPH_CAPACITY_EXCEEDED`), no influence-derived
coordinates and no silent truncation. Copies of static roots are isolated per
request so removing claims cannot leave phantom links in the process cache.

## Accepted social direction and remaining work

Owner confirmed in this chat on 23 October:

1. A link and support are separate actions.
2. For user content, support endorses a version; changed text requires explicit
   reconfirmation. Later clarification exempts Git-owned points: an accepted Git
   update automatically carries active support forward with historical provenance.
3. Anyone registered on the instance may propose a replacement for any one point,
   at most once in a rolling 24 hours across the server. All Git-owned points
   are protected from community voting, including game/lore roots. An author
   with active subscribers also uses voting; direct edits are for zero-subscriber
   non-Git author points only, including UI-owned site welcome text. Site theme/
   domain configuration is a separate owner authority.
4. Notify subscribers durably and include proposals in their feed. Show old/new
   text (side by side or escaped diff). Anyone may support the proposed version,
   including newly arriving subscribers. New arrivals initially endorse the old
   base version and may then explicitly switch. At voting close, adopt if new
   votes exceed old votes; ties retain the base. Default is 72 hours. Immediate
   early adoption is allowed when every current active subscriber explicitly
   supports the new version, with at least one subscriber and no waiting period.
   Scheduled configurable bounds are 24 hours–7 days; empty points cannot
   auto-adopt. Activity-based duration is future policy.

Not yet implemented: subscriptions/support, proposal voting, inbox/feed delivery,
majority/expiry processing, trust/mass, authenticated embed, self-service Git
imports, federation/profile sync. Do not expose a proposal endpoint that silently
falls back to direct author writes. The majority rule is confirmed above;
no automatic adoption is enabled in P05c.

Next packet should add revision subscriptions, proposals tied to a base revision,
private durable inbox plus feed, and explicit protected-point policy. Every
adoption must atomically recheck base revision, pinned target revisions, protection,
unique user support and the approved close-time old-versus-new count/time rule.
Stale proposals need rebasing rather than overwriting newer text. Author writes
and source changes must preserve revision consistency. Imported content needs a recorded
Git authority and automatic support-transfer/changelog contract. Git points do
not receive community overlays; accepted repository updates become current
without a community vote, under the existing source authority checks.
Add rollback/race/expiry and new-user-majority tests before enabling that packet.

Until that packet exists, direct author edits are the original author-only
behavior and there are no subscribers whose support could be transferred.
Normal backup-first application deploy runs the online migration; no new site
registration, content fork or deploy-tool update is needed. Downgrade drops the
publication/receipt/citation registry; use backup/review instead of treating it as
lossless rollback after real authored content exists.

Detailed next packet: [revision proposals](REVISION-PROPOSALS-PLAN.md).
