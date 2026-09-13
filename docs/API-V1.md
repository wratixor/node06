# NODE06 service/API v1 contract

Status: target, not implemented. Updated 13 September 2026 from the original
single-site API draft. The owner's current direction is a common service for
Neocities Free/other independent sites, with a bridge, full iframe and hosted
frontend. [Implementation plan](IMPLEMENTATION-PLAN.md),
[embedding](EMBED-V1.md), [Git roots](ROOT-IMPORT-V1.md).

## 1. Ownership and shared graph

One backend/PostgreSQL database, one shared public meaning-space and common
service users. A site is a separate entity from a user. Its site point is its
welcome page/default entry, linked to the core `all-sites`. Site IDs and root
namespaces are ownership/provenance boundaries, not separate graphs. The planned
open-lore frontend joins this same space; canonical editing is permissioned,
but ordinary users may link to and discuss those public points.

Core/site root Markdown is canonical in its registered Git source; ordinary
points and UI-managed site welcome live in DB. Amsterdam additionally serves
hosted/bridge/full-embed frontend artifacts. This supersedes the earlier
JSON-only host restriction; the domain API itself remains JSON.

No game/wallet authentication or balance integration is implicit. A later plain
wallet support link is ordinary navigation, not a billing callback or entitlement.

## 2. Stable IDs and data

- Core roots keep existing slug IDs; planned core directory ID `all-sites`.
- User `u_<uuid32>`, ordinary authored point `p_<uuid32>`.
- Site `s_<uuid32>` is also the ID of its welcome point; no duplicate user account
  or extra source of influence is created for the site.
- Git root `r_<site_uuid32>_<stable_local_id>`. Explicit local manifest ID survives
  rename. Unknown IDs do not authorize anything.
- Content revision `v_<uuid32>` is immutable and separate from point identity.
- Handles are unique normalized account labels; point bodies need no title/type.

Required data groups:

| Tables | Rules |
|---|---|
| users/sessions | Common account, Argon2id password, opaque token digest, expiry/revoke/active |
| sites/site_members/site_claims | Verified origin, explicit ownership/roles, welcome source/theme, lifecycle |
| points/point_revisions | Current revision pointer + immutable authored body/declared refs/provenance/time/editor |
| root_sources/root_revisions | Registered source, namespace, immutable SHA, candidate/active import |
| point_edges/edge_claims | One undirected semantic edge PK(a,b), a<b; multiple distinct provenance claims |
| point_reactions/reaction_history | PK(user,point), value±1, endorsed_revision, confirmed/pending; history of changes |
| user_supports | Unique non-self global user trust relation |
| events/notifications | Commit order, operation ID/version, source/target revisions; durable own inbox/cursors |
| embed_grants | Scoped user+site+parent-origin+capability+expiry, no global token in parent |
| idempotency_keys | Actor/operation/key, request digest, one committed result |
| calculation_runs/derived | Cutoff, input/config/version/digest, complete published snapshot |
| site_plans/usage_counters | Resource entitlements/atomic meters; no votes/canon for money |
| moderation_actions | Explicit authority/provenance, private reasons separate from public status |

FK/check/index constraints enforce these rules. Canonical edge pairs have a
secondary index in reverse traversal order. Revisions and reaction queries must
join the correct published/endorsed revision; no stale mass attached to new text.

## 3. Point content and author editing

An ordinary author may create and edit their own point's body and declared
references. A site owner/editor may edit its welcome according to assigned
rights. Git-owned points are edited through their source/import, not silently
written by the UI. Coauthors are explicit future assignments, never inferred
from graph proximity. Operator moderation is a separate audited action.

This owner request supersedes the original blanket “edges only at creation”:
editing a point's authored references may add/remove relations involving **that
owned point**, through its versioned edit operation. There is still no API that
lets someone connect two arbitrary other people's existing points. Removal of
one authored/source edge claim cannot remove another claimant's relation.

Content revision changes on body/meaning-bearing authored reference changes.
Inbound references by someone else, theme/layout, views, no-op imports and
presentation timestamps do not revise target meaning. A meaningful edit includes
revision and event atomically, optimistic concurrency and supporter notification.
Server rechecks author/source authority and current revision in the transaction.

Every create/edit text may contain optional labelled point links. Author chooses
which words are links; no automatic linking merely because a known word appears.
Chosen IDs, not text matching, establish the graph. Authored references are
parsed server-side; submitted target lists must agree with parsed links plus
explicit structural targets. Repeated word links to one point yield one edge
claim, not extra mass. Unknown/private targets are rejected.

## 4. Revision-aware endorsement and notification

Proposed safety rule for the user's positivity→eugenics example: an endorsement
is of the **revision the user read**, not arbitrary future content at that ID.
After a material edit, older support/opposition is `pending` for the current
revision and cannot be displayed as agreement/disagreement with the new text.
Previous author/revision/reaction history remains inspectable unless moderated
redaction applies. No semantic AI classifier decides whether a change matters:
all authored text/reference changes count in MVP, avoiding bypass by euphemism.

Affected supporters receive a persistent service inbox item: point, author,
old/new revisions, safe preview/diff and actions `reaffirm current`, `oppose
current`, `remove`. Opponents may also receive change notices; at minimum their
old opposition is excluded from current geometry until confirmed. A notice
appears across all sites for that user; owner/parent cannot read the private
inbox through a public bridge. No email/push implied by this MVP.

An edit queues durable notification work in its transaction. Large audiences
are fan-out asynchronously with a stored recipient cutoff/old-endorsed-revision
and idempotent unique keys. Retry cannot lose recipients or create duplicate
notices. Group successive edits in the inbox while preserving full revision
history; confirmation always checks latest revision. User may mute notices but
that does not automatically reaffirm content. Import batches follow the same
rules. Reverting text does not automatically resurrect old support.

**Budget proposal:** pending positive endorsements retain their allocation slot
but deposit their share in `held_pending`, not into the edited point or other
points. This avoids silently endorsing replacement text or boosting neighbours.
Opposition never gets positive budget. Author edit does not freeze an entire
user's influence, only the changed supported targets. Removal/reaffirmation is
explicit. Publishing derived state atomically with content revision gating
ensures an older snapshot's mass is never displayed as current-revision support.

API raw response can expose exact current confirmed/pending counts immediately;
derived values carry run+content-revision metadata. If run does not match current
revision, `mass=null`, `geometry=null`, `calculation_pending=true` until rebuilt.
Historical mass is available only labelled for the old revision.

## 5. HTTP routes

All below are planned. Prefix `/api/v1`; authenticated calls require authorized
service or scoped embed identity. Bridge has a narrower allowlist than HTTP.

### Public and authentication

```text
GET    /health
GET    /ready
GET    /meta
POST   /auth/register
POST   /auth/login
DELETE /auth/session
GET    /me
GET    /me/notifications?cursor=...
PUT    /me/notifications/{id}/read
```

Login/recovery/management run on trusted hosted UI. Embeds use reviewed
single-use authorization/code exchange and grants from EMBED-V1. Public
registration creates one account, not an account per site.

### Sites and Git roots

```text
POST  /sites                         # pending claim
POST  /sites/{site_id}/verify
GET   /sites/{site_id}               # public config + welcome point ID
PATCH /sites/{site_id}               # owner config, revision precondition
GET   /sites/{site_id}/usage         # owner only
POST  /sites/{site_id}/sources       # register/prove repo association
POST  /sites/{site_id}/imports       # prepare candidate from registered source
GET   /sites/{site_id}/imports/{id}
POST  /sites/{site_id}/imports/{id}/accept
```

Activation atomically creates site point and directory edge. Claim proof/source
verification is a bounded executor, never arbitrary URL-fetch API. Welcome text
editing uses the point revision endpoint, or registered Git source if Git mode.
Source settings and privileged management are absent from bridge commands.

### Graph, editor and signals

```text
GET    /points/{point_id}
GET    /points/{point_id}/field?depth=2&cursor=...
GET    /points/{point_id}/neighbors?cursor=...
GET    /points/{point_id}/revisions/{revision_id}
GET    /points/{point_id}/revisions?cursor=...
GET    /points/search?q=...&cursor=...&source=...
POST   /points
PATCH  /points/{point_id}
PUT    /points/{point_id}/reaction
DELETE /points/{point_id}/reaction
GET    /users/{user_id}
PUT    /users/{user_id}/support
DELETE /users/{user_id}/support
GET    /feed?mode=global&cursor=...
GET    /feed?mode=mine&cursor=...
```

Create example (illustrative short IDs):

```json
{
  "body": "Считаю, что [воля](md://point/r_example_will) влияет на длительность воздействия.",
  "links": ["r_example_will", "s_example"],
  "link_revisions": {"r_example_will": "v_seen"}
}
```

Inline occurrences and explicit structural targets are unioned/deduplicated.
Selected target revision is recorded for citation meaning, while the structural
edge still points to the stable point. Reader can open cited explanation and
see that a newer version exists. On creation/edit, if a selected current revision
changed since search, return 409 TARGET_REVISION_CHANGED and offer compare/reselect
or explicitly cite the old accessible revision. Do not silently substitute it.

Patch includes `expected_revision` plus complete new body/authored references,
Idempotency-Key; 409 on edit collision. A user can edit only owned `point_id`,
not inject edges among arbitrary targets. Link edit changes source meaning,
not its target's authored revision. Git-controlled targets return a source-owned
error with safe source link when UI edit is attempted.

Reaction payload:

```json
{"value": "support", "revision_id": "v_current"}
```

Server checks exact current revision atomically; response409 if stale. Same
value+revision is no-op. Same value with new revision is explicit reaffirmation,
records event and releases held budget into that revision. DELETE removes
confirmed/pending reaction idempotently. One user has at most one current stance
per point globally, regardless of site. Self user support API rejects explicit
self because trust already includes self retention.

### Response shape

Point: id/origin/current_revision/body or source reference, lang/provenance,
links and bounded edge data, created/content_updated/last_interaction times,
confirmed/pending reaction counts, stats+geometry with run/revision/version,
my_reaction including endorsed_revision/state for authenticated user, can_edit
as server-owned hint (authorization still rechecked on write).

Root static content remains canonical in its accepted source; service snapshot
is a cache/projection. A site client can fetch a needed shared root from the API
rather than download the entire root forest. No endpoint exposes a private repo,
internal lore or account session through `origin=root`.

## 6. Fast semantic-link search

Typed suggestions or selected phrase open search across **the full shared graph**,
including site roots and public lore. UI proposes candidates; never silently
turns all occurrences into links or declares a word has one true meaning.
Defaults: 200ms debounce, min2 chars except exact ID, <=20 results/page, max
query128 characters, cancellation/generation guard. Allow keyboard selection,
Enter/Esc, selection→link, remove-link without deleting word, multiword phrases.

Candidate fields: stable point ID, current revision, safe short snippet,
source/site, author and reviewed-source marker. Bodies still have no mandatory
title; display label may come from matched phrase/preview. Several «воля» entries
can coexist with distinct explanations. Prefer exact phrase/alias hits, then
text relevance with deterministic tie-break; do not rank paid sites first.
Source/lore filters are optional discovery aids, not isolated spaces.

MVP indexes PostgreSQL full text for Russian/English with language-aware inputs
and a reviewed substring/prefix strategy (e.g. pg_trgm if installed/approved).
Store explicit aliases only if owner-authored/validated; morphology does not
merge IDs. Benchmark response latency and index update time; safe snippets,
bounded queries, prepared parameters and hidden-content filtering mandatory.
No vector/model service required. Search labels and selected spans are plain
text, not HTML trusted from API. Client does not see giant global index.

Example «воля → длительность воздействия» is an author's claim linked to a
chosen lore explanation, **not an approved new combat formula**. If the relevant
lore root is not yet public/imported, offer no fabricated official result;
create a separate proposal point or import reviewed text later.

The selected definition's author does not thereby endorse the surrounding post.
An independently debatable causal statement may be its own ordinary point with
links to both concepts; this needs no mandatory relationship type or ontology.

Link vs support: pending decision captured in the implementation plan. Default
proposal is semantic citation only, plus explicit “also support this revision”.
If chosen, support is a separately recorded authorized action with budget
semantics. No invisible self-support or vote per repeated word occurrence.

## 7. Trust, feeds and derived state

Influence introduced once per active common user. Suggested T1:

```text
T[i,j] = 1/(k_i+1) for self + explicit supported active people
w_next = (1-d)*ones + d*T^T*w ; proposed d=0.5
people_i=0.5*w_i ; points_budget_i=0.5*w_i
n_i = number of user's positive confirmed OR pending endorsement slots
confirmed slot -> points_budget_i/n_i into supported revision
pending slot -> points_budget_i/n_i into held_pending
no positive slots -> points_budget_i into idle
```

`sum(w)=N`; `sum(people)+sum(current_mass)+held_pending+idle=N` within tolerance.
Sites, forks, assets and directory edges introduce zero base influence. Negative
reactions affect a separately designed geometry signal, never positive mass.
Revisions/notification/reaffirm events are calculation input; snapshot joins
must not leak stale mass to changed text. Formula is a proposal, not fixed lore.

Six raw components + confidence + version, never RGB substitute. Unresolved
coordinates null; synthetic visual layout labelled. Snapshot job reads frozen
commit-ordered input, validates conservation/determinism and publishes a complete
run; failures retain labelled last-good. No per-request recursive calculation.

Global feed is chronological operations, grouped edits visible. Mine covers
new points from supported authors or linked to supported points; own revision
notices are delivered independently even if a support is now pending. Cursor
has fixed cutoff/filter revision/last sequence; no offset pagination, no trust
spam fan-out. Views do not count as interactions.

Preserve the initial activity contract: changed/added/removed reactions and a
newly attached point update affected points' `last_interaction_at`. Versioned
author edits update the source point; changed reference claims update affected
endpoints once per operation. No-op writes/imports, viewing and notifications
being read never bump activity. Server UTC timestamps and commit sequence are
authoritative, not browser clocks or checkout mtimes. Cracked/abandoned styling
may be derived from inactivity, not a stored `abandoned=true`, and must not
silently decay endorsement mass. Rate limits cover edit-based feed bumping.

## 8. Validation and limits

Suggested body1–8192 characters/32KiB UTF8, 1–16 authored targets (sites/core may
use bounded import policies), field200 nodes/600 edges with explicit truncation;
all-sites has directory paging instead of unbounded depth2 expansion. Feed30,
max100; root importer stricter file/source quotas. Enforce before expensive work.

JSON errors include code/message/request_id. Standard 401/403/404/409/413/422/429
with Retry-After/503; no SQL/tracebacks/secrets. Session responses no-store.
CORS exact allowlist for opted-in direct clients; same-origin embed API uses
scoped authorization, not trusting parent claims. PostMessage has separate checks.

Tests: cross-site single identity/vote; authorship editing vs unrelated neighbour;
concurrent edit/reaction revision race; pending support no new-content mass;
notification retry/cutoff/bulk import; explicit reaffirm/remove; stale snapshot
revision gating; semantic search homonyms/RU/EN/unlinked word/repeated targets;
source ownership/SSRF/limits; unsafe Markdown; trusted auth/iframe policies;
conservation with pending holds; root source rollback retains global history.
