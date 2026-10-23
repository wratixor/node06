# First-party point authoring v1

Source implementation, 23 October 2026; deployment is a separate state. This
slice is P05c, not a completed social layer. Public reads/bridge reuse the same
published content; writes happen only on the configured management origin.

## User workflow

Open `/editor/` (also linked from Account and the hosted header), sign in via
`/account/`, choose links and write text. No language selection or language suffix is required
for a user point; root IDs authored with RU/EN suffixes are just existing content. No site registration is required. Select words and use
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
   including newly arriving subscribers. Initial subscription to the old base
   is not a ballot. Only explicit old/new votes during the proposal count;
   nonvoters contribute to neither total. A vote atomically switches subscription
   to the chosen version. At voting close, adopt if new influence exceeds old
   influence; equal influence retains the base. Default is 72 hours. Immediate
   early adoption requires explicit new-version ballots covering 100% of all
   current eligible subscribers' influence, with positive total influence.
   Silent subscribers are absent from the normal tally but their uncast positive
   influence prevents early completion. Zero-weight accounts do not block it.
   Scheduled configurable bounds are 24 hours–7 days; empty points cannot
   auto-adopt. Zero-total influence never auto-adopts. Activity-based duration is
   future policy.

The social v1 packet now enforces subscriber-aware edits and adds subscriptions,
proposals, explicit influence-weighted ballots, private inbox and trust:
[SOCIAL-V1](SOCIAL-V1.md). Authors may directly edit only non-Git points without
active subscribers. Git roots remain protected and transfer support automatically
on accepted source updates. Authenticated embeds, signed reactions, self-service
imports and federation remain future work.

Normal backup-first application deploy runs the online migration; no new site
registration, content fork or deploy-tool update is needed. Downgrade drops the
publication/receipt/citation registry; use backup/review instead of treating it as
lossless rollback after real authored content exists.

Detailed next packet: [revision proposals](REVISION-PROPOSALS-PLAN.md).


Influence correction, 23 October: subscription counts are not voting weights.
Binding adoption depends on authoritative versioned influence snapshots; do not
use headcount as an interim implementation. T1 was subsequently explicitly approved for v1 with conservation checks; see
SOCIAL-V1 for the numerical contract.

## Contextual editor and account favorites — 23 October 2026

The field text panel and shared search detail expose **Add related point** on
static, hosted and full-iframe copies. The link opens the trusted management
origin's `/editor/?from=POINT_ID` in a separate tab. This creates a NEW point;
it does not try to edit the source (including protected Git roots). After login,
the editor reads the current public source and preselects its exact revision/digest
as a connection. Unavailable sources are explicit errors, not silently dropped.
The account opens separately and **Continue after login** reloads the same editor
URL with its source context; passwords never enter an embedding parent's page.

The editor uses the same search field/magnifier/results component as the site,
placed next to its selected links rather than requiring a search in the header.
Search is rectangular across the whole frontend. Select a result to add a link;
selected textarea words become an explicit semantic Markdown link. The textarea
is resizable, chosen targets show readable previews, and My points is collapsible.

Private favorites are bookmarks of point IDs, not a second taxonomy or automatic
subscription. Save a selected target with ☆; use + in favorites to add it to the
current text. Existing links, proposals, influence and support stay unchanged.
Favorites belong to the local account, so the same user sees them across connected
sites on this instance. Different instances do not synchronize them. Every use
fetches the current public target pin; it does not reuse an old favorite revision.
Removing a link does not remove the bookmark, and removing a bookmark does not
remove an already selected link. At most 64 favorites per account.

Migration `0011_favorite_points` adds `(user_id, point_id)` with foreign keys.
`GET /api/v1/me/favorites` returns private bounded current previews/pins. An
unavailable saved target is marked unavailable and remains removable. Same-origin
CSRF/idempotency-protected `POST /api/v1/me/favorites/{id}` with `{active: bool}`
sets/removes membership; only currently public targets can be added. There is
no public favorites directory and no authenticated favorite API on the embed host.

Apply the online migration through the normal backup-first deploy after merge.
Downgrade drops favorites; it does not remove authored points or subscriptions.
Validation: disposable PostgreSQL privacy/CSRF/replay/cap/removal tests, packaged
wheel HTTPS browser workflows for saving/reusing favorites and contextual creation,
mobile overflow and existing lost-response publication checks. This source packet
is not a claim that production has already updated.


### Editor order update — 23 October 2026

Neither the first-party editor nor the proposal form asks for language. Newly
authored points use the existing neutral API default, while editing/proposing
retains existing metadata internally so ordinary text edits do not rewrite it.
User IDs are generated independently of language; no suffix is required. Root
IDs, imports and public API metadata stay compatible. This is UI work, not a
localization feature or a migration.

The editor places search, selected connections and favorites above the text.
My points and published history are collapsible above these controls. Text is the
last editing section, followed only by Publish. Proposal reference controls also
precede the candidate textarea. The shared picker remains outside the publication
form to avoid nested-form submission. Selection links, receipts and draft
retention continue through the same handlers.

The owner requested a minimal post form: no permanent explanatory paragraphs or
section headings. Tags use compact chips (open, star for favorite, × for remove),
favorites show as + buttons and disappear when empty. Tooltips/accessible names
explain icon actions without filling the form. Search/tags precede a small Link
toolbar, textarea and right-aligned Publish. My points/history/open link remain
compact above the form; failures still show actionable status and preserve drafts.
No new title field, rich-text formats or unsupported media toolbar is introduced.
