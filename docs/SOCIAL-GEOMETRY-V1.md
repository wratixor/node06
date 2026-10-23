# Social geometry v1

Owner-approved opposite-pair option (23 October 2026). This replaces the earlier
subtraction/PCA candidates in the implementation plan. Source completion does not
mean deployment or a live Neocities check.

## Coordinates, color and projection

A local active account has six positive integer coordinates, each `1..65535`.
The default is `[128,128,128,128,128,128]`. These are chosen coordinates, not
measured personality traits. Account settings at `/community/#my-color` expose
six independent numeric coordinate fields in the root coordinate order: Body,
Spirit, Onslaught, Composure, Reaction, Technique (internal mapping only).
The public form shows six colored markers matching the field rays, without stat
names or semantic axis labels. Accessible names identify colors, not stats.
Every field accepts the full existing
API range, `1..65535`, with integer steps. The old fragment stays compatible.

Color is a read-only projection of these stats. Changing one stat never sets its
opposite to `256-v`, and loading/saving never reconstructs coordinates from RGB
or silently normalizes raw values. Empty, fractional or out-of-range fields block
submission and clear the preview until corrected. This replaces the earlier
three-slider RGB interface, not the geometry/T1 calculation or stored profiles.

The component marker order is red `#ee484a`, cyan `#00d2dc`, green `#3ece70`,
magenta `#d646d6`, blue `#4170ee`, yellow `#f0cd2c`, matching the renderer.

Normalize each user's vector to a sum of `10^12` by exact integer division and
largest remainder, breaking ties by component index. Scaling all six raw values
by the same factor therefore changes neither normalized coordinates nor weight.
No zero, signed component, epsilon, inferred semantic label or text classifier.

The existing renderer order is authoritative:

| Components | Positive direction | Opposite direction | Color channel |
|---|---|---|---|
| 0,1 — Body, Spirit | +x, red | -x, cyan | R = 255 A/(A+B) |
| 2,3 — Onslaught, Composure | +y, green | -y, magenta | G = 255 C/(C+D) |
| 4,5 — Reaction, Technique | +z, blue | -z, yellow | B = 255 E/(E+F) |

Channels round half up to integers. Color is a projection of coordinates, not
additional influence. The local relative axis remains
`(target_positive*center_negative - target_negative*center_positive) /
(target_positive*center_negative + target_negative*center_positive)`.
The existing bounded sphere/depth projection is unchanged. Equal relative
coordinates still need a deterministic display direction to separate nodes;
that direction is not an extra semantic coordinate. Sphere radius still uses
link degree. Confidence, disagreement metrics and mass-based radii are deferred.

## Reactions and finite budget

A **subscription** uses the normalized vector unchanged. An explicit **block**
uses `[B,A,D,C,F,E]`. Blocking is the opposite-pair contribution, not literal
negative component subtraction, a vote for the old revision, or content removal.
Ordinary non-subscription, unsubscribe and unblock are neutral.

At most one active subscription or block may exist for one user/point. Switching
is atomic under the existing graph transaction lock. Blocking withdraws the
actor's open ballot; explicit voting switches back to support and clears a block.
A block does not enroll a subscriber, deliver subscriber notices or veto early
adoption. Authors still need voting when there are active positive subscribers.

T1 recursion and the 50/50 people/point split stay unchanged. The point half now
splits over the **union of active public subscription and block slots**, with
integer remainder by point ID. A block cannot use a second full budget.
Model: `t1-v2-d0.5-q12-signed-slots`; geometry: `opposite-pairs-v1-q12`.

For a point, sum each confirmed vector times its allocated T1 share, then divide
by total confirmed contributing shares. Largest remainder again gives exactly
`10^12` positive units. Both signs take part in geometry. Positive support and
blocked influence remain separate aggregates; the latter is not called support.
Only positive subscription allocations participate in old/new revision ballots.

Conservation is checked before publication:

- effective user weights sum to `N * scale`;
- people budget is exactly `N * scale / 2`;
- confirmed positive + confirmed blocked + held old-version + idle point budget
  is exactly `N * scale / 2`.

A missing/retired public point is excluded from active slots, as in T1 v1. An
old reaction on a still-visible point reserves its slot, but contributes no
current geometry until its current version is confirmed.

## Versions and Git authority

Both reactions pin a real revision/digest; static roots pin a digest/body with
null revision. Normal revision changes leave old support and blocks on their old
pins. Both need explicit confirmation for the new text. Pending contributions
reserve budget without being relabelled as current support/opposition.

Accepted Git updates represent source authority: they transfer **both** existing
support and block pins automatically, audit each previous pin in support history,
and publish the normal source changelog. Blocks do not grant source editing
rights. A first static block establishes the source baseline before later sync.
Removal never invents a new supported or blocked text.

No confirmed contributions means `coordinates=null`, not fake neutral influence.
The renderer preserves a root's original seed, or its labelled display-only
layout for authored/site points. With real neutral contributions, the result is
a real neutral vector; deterministic display separation is still required.

## API, bridge and UI

Private first-party APIs use the existing session, allowed Origin, CSRF token and
actor-scoped idempotency receipts:

- `GET /api/v1/me/geometry` → own raw coordinates and hex color.
- `POST /api/v1/me/geometry` with `{coordinates:[six integers]}`.
- `POST /api/v1/points/{id}/block` with `{active,revision_id,content_digest}`.
  Adding/reconfirming requires the current public pin. Removing works with a
  stored pin even when a point has retired. Replays do not double-spend.
- `GET /api/v1/me/blocks?after={point_id}&limit=30`, max 50 per page.
- Own `/me/subscriptions/{id}` also returns own `block` or null.

Public `GET /api/v1/geometry?ids=id1,id2` and bridge `points.geometry` share
`node06-geometry/1`: snapshot ID, pending flag and items containing ID,
revision/digest, nullable coordinates/color, geometry model and pending status.
1–64 unique valid IDs; invisible/retired IDs are omitted. No user IDs, raw user
profiles, individual reactions, arbitrary URLs or credentials are returned.
PostMessage params are exactly `{point_ids:[ids]}`; bridge HTTP encodes a comma
list. Existing origin/channel/source/rate/response-size controls remain in force.

The hosted field, full iframe and static frontend all use this same anonymous
transport. The static parent never fetches an external API or sees auth state.
Visible IDs are read in batches of 64, at most 1024 total per field request;
a larger field reports capacity explicitly and retains its current layout.
Mixed snapshot IDs, incomplete visible-point batches, stale center responses
and wrong text pins cannot overwrite current geometry. Coordinates disappear back to the saved seed after the last
confirmed reaction is removed. No geometry request is triggered by each drag.

Snapshot writes run in the existing worker (about 30 seconds). Changing a color
or reaction marks old output pending; the field offers **Refresh geometry** and
refreshes on focus/center changes. It does not poll continuously. Last-good
coordinates are usable only for matching text pins, with pending status visible.
A read failure retains the last layout and says unavailable, never fresh zero.

## Migration and rollback

`0012_social_geometry` follows `0011_favorite_points`. It adds `user_geometry`
and version-pinned `point_blocks`; no existing author content is rewritten.
Each DDL command is separate, using the project's actual psycopg migration path.
Run online upgrade against a disposable PostgreSQL instance before release.

Before deployment, back up the service DB; deploy matching frontend/backend and
apply the normal online migration. A downgrade to 0011 deletes new profile/block
state, so preserve the backup. Existing author content/subscriptions survive the
migration round trip. Old immutable influence rows stay historical; the new
projection identity forces a new run rather than modifying old snapshots.
Old clients can ignore additive fields; old bridges reject only the new method.

## Compact point actions and authors

The field/search detail replaces the former support explanation panel with a
four-icon toolbar: subscribe, block, related post, favorite. Active states use
aria-pressed; each icon has a single-language tooltip/accessible name. Normal
support/status paragraphs are removed. Only failure/stale-text messages appear.
The main Community link follows the selected point for revision comparison.

On the management host, authenticated reactions/favorites act in place through
existing CSRF/idempotent endpoints. Lost acknowledgments retain the exact request
for replay even if a subsequent personal read sees its committed state. On a
static parent/full iframe, icons are links to the management host with an explicit
intent; GET never performs a mutation. The user confirms the action in the
trusted first-party interface. Passwords, cookies and private reaction lists do
not pass through the bridge. Favorites do not spend influence.

Public point detail/graph exposes author attribution: original user ID/handle,
site owner for site points, source maintainer for imported Git roots, system for
the shared directory. Static roots without a recorded person identify their Git
source rather than inventing a personal author. The small public social summary
includes attribution name/kind, but no author ID or subscriber IDs. These are
source/maintenance attributions, not a claim about individual Git commit authors.

After successful creation or editing, the editor opens the published point with
`p` and `open` pins in the relevant hosted entrance. The related-post icon carries
`return_to` from its current site; only `/` or `/sites/s_<32 hex>/` is accepted.
External/invalid return URLs fall back to `/`. Failed writes and lost responses
retain the editor draft; only a confirmed success clears it and navigates.

On the management host, NEW POINT/related-post links now open a same-origin editor
modal over the current map. After publication the parent shows the new point.
Standalone URLs remain supported. Account/auth pages are not made embeddable;
only editor HTML allows its own origin. External Neocities/full frames keep
trusted navigation until authenticated external embedding is designed. The
protocol and draft-close rules are maintained in POINT-AUTHORING-V1.

## Validation evidence — 23 October 2026

Full disposable PostgreSQL suite: 236 passed. Installed-wheel HTTPS Chromium
acceptance passed hosted/full/static anonymous reads, current tag pins,
one-click tag selection/direct article links, reaction budget states, color,
block/unblock, lost favorite acknowledgments, safe author attribution, modal
create/edit, canceled draft close, publish navigation and cookie isolation.
Migration upgrade and populated downgrade/re-upgrade use the actual psycopg path.
Lint, formatting, JS syntax, protocol checks and static build passed. These are
local fixture checks; production deployment and real Neocities post-release
verification remain separate.
