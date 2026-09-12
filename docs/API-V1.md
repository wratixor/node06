# NODE06 backend/API v1 contract

This document fixes the intended boundary for the future social backend. It is a design contract, not an implementation yet.

Owner direction, 12 September 2026: NODE06 is the rethought concept engine.
The target service belongs in this repository's `backend/`, while deployment
stays separate from the Neocities frontend and Wagtail. Read
[IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) for delivery packages, verified
Neocities Free CSP restrictions, language/identity rules and unresolved
trust/geometry decisions. Its explicitly marked proposals are not silently
ratified additions to this contract.

## 1. Purpose and boundary

The Neocities site remains a static HTML/CSS/JS client and the Git repository remains the canonical source of root Markdown points.

The backend is a separate API service. It does **not** render NODE06 HTML and does **not** become the canonical home of root texts.

The backend owns only dynamic/social state:

- accounts and sessions;
- user-created points;
- dynamic point relations created together with a new point;
- support / opposition reactions;
- delegated trust between users;
- chronological activity events;
- derived weights, masses, coordinates, colors and confidence values;
- a cache/registry of root IDs and root-root relations imported from the current static build index.

The service must be deployable independently from `geno-dice.com` and its Wagtail application.

## 2. Suggested implementation stack

Start small:

- Python;
- FastAPI;
- PostgreSQL;
- SQLAlchemy 2.x;
- Alembic migrations;
- Pydantic models through FastAPI;
- Argon2id password hashing;
- opaque revocable bearer sessions stored server-side.

Do not add Redis, Celery, Kafka, WebSockets or a template engine until an observed requirement justifies them.

Suggested repository layout:

```text
backend/
├── pyproject.toml
├── alembic.ini
├── alembic/
├── app/
│   ├── main.py
│   ├── config.py
│   ├── db.py
│   ├── api/
│   │   ├── auth.py
│   │   ├── points.py
│   │   ├── users.py
│   │   └── feed.py
│   ├── models/
│   ├── schemas/
│   └── services/
│       ├── root_sync.py
│       ├── trust.py
│       ├── geometry.py
│       └── feed.py
└── tests/
```

`trust.py` and `geometry.py` should remain deterministic calculation modules rather than being hidden in ORM model methods.

## 3. IDs

All objects exposed by the API use stable string IDs.

Root point IDs remain the Markdown filename without `.md`, for example:

```text
charter-en
observation-ru
```

User-created point IDs should use an unambiguous generated prefix, for example:

```text
p_<ULID>
```

User IDs should use a different prefix:

```text
u_<ULID>
```

The exact generator can be selected during implementation, but IDs must be globally unique and must never depend on point text, file paths or handles.

## 4. Root synchronization

The static build should expose a machine-readable root snapshot, for example `dist/data/points.json`.

The backend periodically or during deployment imports from it only:

- root IDs;
- creation/update metadata available in the static build;
- root-root relations.

Root Markdown text remains canonical in Git/Neocities. A database row for a root point is only a registry/cache record required for foreign keys, reactions and dynamic relations.

The sync operation must be idempotent. It may update derived root registry data, but it must never overwrite user-created data or pretend that DB text is canonical for root points.

## 5. Database schema

Names below are conceptual. Exact SQL types may be adjusted during implementation.

### `users`

```text
id                  text primary key
handle              case-insensitive unique text
password_hash       text
c1..c6               numeric/null initially
created_at          timestamptz
is_active           boolean
```

The six color/position components may initially be nullable until the social geometry UI is enabled.

### `sessions`

```text
id                  text primary key
user_id             -> users.id
secret_hash         text unique
created_at          timestamptz
expires_at          timestamptz
revoked_at          timestamptz nullable
```

The browser receives the opaque secret once and sends it as `Authorization: Bearer ...`. Store only its hash server-side.

### `points`

```text
id                  text primary key
author_id           -> users.id nullable
origin              enum(root, user)
body                text nullable
created_at          timestamptz
last_interaction_at timestamptz
```

Rules:

- `origin=root`: `body` may be null because Markdown/Git is canonical;
- `origin=user`: `author_id` and `body` are required;
- a point has no title/type/category field;
- external media are ordinary URLs inside point Markdown/text in v1.

### `point_edges`

```text
point_a             -> points.id
point_b             -> points.id
created_by          -> users.id nullable
created_at          timestamptz
origin              enum(root, user)
primary key(point_a, point_b)
```

Store a pair in canonical order so `(A,B)` and `(B,A)` cannot both exist. Require `A != B`.

The relation is semantically bidirectional.

**There is no API for connecting two arbitrary existing points.**

User-origin edges are created only as part of creation of a new user point. If a new point `C` is created with links `[A,B]`, the backend atomically creates `C`, `C↔A` and `C↔B`.

### `point_reactions`

```text
user_id             -> users.id
point_id            -> points.id
value                smallint  (+1 support, -1 oppose)
created_at          timestamptz
updated_at          timestamptz
primary key(user_id, point_id)
```

A user has at most one current reaction to one point. Changing support to oppose updates the row; removing a reaction deletes it.

### `user_supports`

```text
source_user_id      -> users.id
target_user_id      -> users.id
created_at          timestamptz
primary key(source_user_id, target_user_id)
```

Explicit self-support rows are not required. Self-support is an invariant of the trust algorithm.

### `events`

```text
id                  bigserial/ULID primary key
actor_user_id       -> users.id nullable
kind                enum
point_id            -> points.id nullable
target_user_id      -> users.id nullable
created_at          timestamptz
payload              jsonb nullable
```

Initial event kinds:

```text
point_created
support_added
support_removed
oppose_added
oppose_removed
user_support_added
user_support_removed
```

This table powers the chronological feed and historical reconstruction. Derived state must never replace the raw event history.

### derived caches (later)

Do not make these sources of truth. They can always be rebuilt.

Possible tables/materialized state:

```text
user_effective_weight
point_mass
point_coordinates(c1..c6)
point_confidence
geometry_version
trust_version
calculated_at
```

## 6. Influence model contract

Every registered user introduces exactly `1.0` unit of base influence into the system.

The initial global split is:

```text
people_budget = 0.5
points_budget = 0.5
```

Keep this ratio server configuration in v1; do not expose it as a per-user preference initially.

### people budget

A user always supports themself implicitly. Their people budget is divided equally between self and all explicitly supported users.

If a user supports `k` other people:

```text
share = effective_people_budget / (k + 1)
```

Received delegated trust changes effective user weight, but endorsement must not create global influence. The trust calculation must conserve the total influence introduced by users and use damping/retention so cycles cannot amplify themselves.

### points budget

A user's point budget is distributed over the points they currently support.

If they support `n` points:

```text
share = effective_points_budget / n
```

Ordinary points are terminal sinks. They accumulate mass but never retransmit influence.

Opposition does not transfer positive mass. It is a separate signal for geometry and similarity.

## 7. Coordinates and color

The public coordinate contract remains six-dimensional.

Do not replace it with RGB. Rendering folds the six components into three opposed display axes only for visualization.

The current Hexrelatum-compatible complementary display ends are:

```text
cyan    <-> red
magenta <-> green
yellow  <-> blue
```

The backend later derives point coordinates from weighted user reactions. The raw six values, calculation version and confidence should be returned by API; the frontend performs visual projection.

New/under-observed points may have `coordinates = null` or low confidence and should visually remain unresolved/free-floating rather than receiving fake authoritative placement.

## 8. Last interaction / decay

`last_interaction_at` changes when:

- the point receives/removes/changes a support or opposition reaction;
- a new point is attached to it.

Reading a point does **not** count as interaction.

The frontend may render long-inactive points with cracked/abandoned styling. This is presentation derived from `last_interaction_at`, not a stored status such as `abandoned=true`.

## 9. API surface v1

Prefix all endpoints with:

```text
/api/v1
```

### health

```http
GET /api/v1/health
```

### authentication

```http
POST   /api/v1/auth/register
POST   /api/v1/auth/login
DELETE /api/v1/auth/session
GET    /api/v1/me
```

Example registration body:

```json
{
  "handle": "catobserver",
  "password": "..."
}
```

Login/register returns an opaque session token plus the public user object.

### point lookup

```http
GET /api/v1/points/{point_id}
```

For root points the API may return root metadata and dynamic state while the frontend continues to obtain canonical root body from its static index.

Example shape:

```json
{
  "id": "cats",
  "origin": "root",
  "author": null,
  "body": null,
  "created_at": "...",
  "last_interaction_at": "...",
  "links": ["pets", "p_01..."],
  "stats": {
    "degree": 18,
    "mass": 4.275,
    "support_count": 42,
    "oppose_count": 3
  },
  "geometry": {
    "coordinates": [0.1, 0.7, 0.2, 0.1, 0.8, 0.4],
    "confidence": 0.63,
    "version": 1
  },
  "my_reaction": "support"
}
```

Unauthenticated responses omit/null `my_reaction`.

### local field

```http
GET /api/v1/points/{point_id}/field?depth=2
```

Return center + unique depth-1 + unique depth-2 objects. A point directly linked to the center must never be duplicated in depth 2.

This endpoint exists so the browser does not need to download the entire dynamic graph.

### create a point

```http
POST /api/v1/points
Authorization: Bearer ...
```

Body:

```json
{
  "body": "A person posting cats cannot be bad.",
  "links": ["cats", "morality"]
}
```

Rules:

- `body` is required but may be very short;
- every target point must already exist;
- duplicate targets are rejected/deduplicated consistently;
- the transaction creates the point and all its edges atomically;
- no standalone create-edge endpoint exists;
- creation updates `last_interaction_at` for all linked points;
- emit `point_created` event.

### point reaction

```http
PUT /api/v1/points/{point_id}/reaction
Authorization: Bearer ...
```

```json
{"value":"support"}
```

or:

```json
{"value":"oppose"}
```

Remove current reaction:

```http
DELETE /api/v1/points/{point_id}/reaction
```

Operations are idempotent.

### user lookup / trust

```http
GET    /api/v1/users/{user_id}
PUT    /api/v1/users/{user_id}/support
DELETE /api/v1/users/{user_id}/support
```

Supporting a user delegates part of the people budget. The backend must reject explicit self-support API calls because self-support is already implicit.

### feeds

```http
GET /api/v1/feed?mode=global&cursor=...
GET /api/v1/feed?mode=mine&cursor=...
```

Use cursor pagination, not page numbers.

`global` is chronological activity.

`mine` initially includes:

- new points attached directly to points the user supports;
- new points authored by users they support.

Do not initially include every reaction made by followed users; that would turn one enthusiastic human into a distributed denial-of-feed attack.

## 10. HTTP / validation rules

- JSON only for the API.
- UTF-8 text.
- Explicit request size limits.
- Sanitize/escape point content when rendering; Markdown must not permit arbitrary HTML/script injection.
- CORS should allow only the production Neocities origin and explicit development origins.
- Rate-limit registration, login, point creation and reactions before public launch.
- Never expose password/session hashes.
- Return stable machine-readable error codes in addition to human-readable messages.

Suggested error shape:

```json
{
  "error": {
    "code": "POINT_NOT_FOUND",
    "message": "Point does not exist."
  }
}
```

## 11. Root + dynamic graph merge in the frontend

During the transition the browser has two sources:

```text
static points.json  -> canonical root body + root topology
API                 -> users + dynamic points + dynamic edges + social state
```

Merge by stable point ID.

The API wins only for dynamic/social fields (`mass`, reactions, `last_interaction_at`, geometry, dynamic links). It must not overwrite the static canonical body of a root point.

Once the API is available, the current static FIELD remains a valid offline/read-only fallback.

## 12. Suggested implementation order in VS Code

Implement in small vertical slices:

1. Create FastAPI project, config and PostgreSQL connection.
2. Add migrations for `users`, `sessions`, `points`, `point_edges`.
3. Implement root snapshot sync and verify root IDs appear in DB.
4. Implement register/login/session auth.
5. Implement `GET point`, `GET field`, `POST point` and edge invariants.
6. Add `point_reactions` + events + `last_interaction_at`.
7. Add `user_supports`.
8. Add chronological global feed.
9. Implement deterministic trust calculation with conservation tests.
10. Add point mass calculation.
11. Only then implement social coordinates/confidence.
12. Add `mine` feed and connect the Neocities client.

Do not implement geometry before raw reactions, trust and event history are trustworthy. Pretty colored mathematics built on broken social state is still broken social state, merely festive.

## 13. Required tests

At minimum:

- root sync is idempotent;
- a point cannot link to a missing point;
- arbitrary old-point-to-old-point edge creation is impossible;
- creating `C` linked to `A,B` creates exactly two bidirectional semantic relations;
- duplicate/self edges are rejected;
- one user has at most one reaction per point;
- reactions correctly update `last_interaction_at`;
- creating a linked point updates neighbors' `last_interaction_at`;
- self support is always included in trust calculation;
- mutual user support cannot create influence;
- total effective influence remains equal (within numerical tolerance) to number of active users;
- point support budget is conserved;
- derived state can be deleted and rebuilt from raw data/events;
- depth-2 field response contains no depth-1 duplicates.
