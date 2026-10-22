# Public current points and prefix search v1

P05a, 22 October 2026. This contract describes implemented source, not a deployed
release. It provides anonymous reads on the configured management/wiki origin:

- `GET /api/v1/points/{id}`: current public point, body/HTML, provenance and links.
- `GET /api/v1/points/search?q=...&limit=20&after=...`: brief matching points.
- `GET /api/v1/points/{id}/neighbors?limit=50&after=...`: brief adjacent points.

No login is needed. No mutation, support, vote, influence calculation, revision
history or point-creation UI is implemented by this slice. Arbitrary query keys
and duplicate parameters are rejected. `/search` is a reserved route.

## Visibility and identity

Reads combine the built static core and the same instance's current DB content:
all-sites, active verified site welcomes, and active accepted operator Git roots.
An imported root must still match the source's owner/origin and accepted revision.
Retired/inactive roots, pending sites, unpublished rows and historical drafts do
not become public through search. Hosted graph reads enforce the same accepted
root revision guard. Core points remain public even if no site references them.

DB results carry their real `revision_id`, a content digest and source metadata.
Static core is not yet persisted as immutable DB revisions: its `revision_id` is
**null**, with a deterministic digest and static-root/build provenance. A digest
is not a revision pin. Do not invent `v_` IDs or offer historic core citation until
core persistence is implemented. `lang` describes a point, never a language route.

A point response includes body, rendered HTML, declared links, current visible
links (first 50), `links_truncated` and `neighbors_cursor`. Declared links describe
authored references; they are not proof that the target is currently public.
Brief items include id, origin, lang, preview, revision_id, content_digest and
source. Search/neighbor responses are `{items: [...], next_cursor: id|null}`.
Only canonical DB edges with surviving provenance claims are traversed. Views
never write or update activity. Private history is deliberately not exposed:
older welcome revisions can contain unpublished drafts.

## Search and bounds

The trimmed query has at most 128 characters and eight Unicode alphanumeric
terms. Matching is an OR of a literal substring of the ID and full-body AND
word-prefix search. Thus `вол длит` can find text containing both `воля` and
`длительность`; an unlinked word remains searchable without creating a relation.
No stemming, semantic ranking, fuzzy matching, endorsement or cross-server fetch
is implied. Punctuation uses the PostgreSQL simple text parser for DB content and
Unicode word splitting for static core; these parsers can differ at compound
words. This is not a claim of identical tokenization for every language.

Python Unicode casefold normalizes both stored search text and queries, including
mixed-case Cyrillic and `Straße`/`STRASSE`, independently of database locale. DB
current revisions are searched with a simple-dictionary PostgreSQL GIN index.
Static core is a small in-memory build projection; new builds include raw `body`
in `data/points.json`. Older bundles fall back to stripped HTML for search and
return null body for those static roots.

Limits are 1–50 items, default 20 search / 50 neighbors. Pages are sorted by ASCII
point ID (DB C collation); `after` is the last ID, not an offset. Page cursors are
not snapshot isolation: edits between requests can change results. Reuse the same
query and deduplicate IDs in clients. Serialized responses above 255 KiB return
413 rather than silently clipping point text. Missing/hidden points return 404;
invalid inputs 400/422, unavailable DB 503 with sanitized codes. Responses use
no-store/nosniff. Query limits bound returned rows, not measured service capacity;
large-scale load/rate admission remains release hardening work.

## Transport and migration

This direct API requires the configured wiki/management origin; it is rejected
on the embed origin. No broad CORS or cookie change is introduced. Neocities Free
must continue using its iframe transport. The existing bridge `points.search`
keeps its older bounded ID/preview substring semantics; it has **not** gained this
full-body search. A later scoped bridge protocol/UI change must explicitly expose
new pagination/search without breaking existing clients.

Migration `0008_point_search` adds derived `point_revisions.search_text`, backfills
it using Python casefold and creates the GIN index. Service SQLAlchemy revision
inserts normalize body in the same transaction; raw SQL importers must supply the
same normalized value. No semantic body/revision IDs are rewritten. The extra
text/index consumes storage; production sizing has not been benchmarked.

Use the normal **online** `alembic upgrade head` deployment. Diagnostic
`alembic upgrade head --sql` remains generatable, but emits an explicit exception
at this migration: offline SQL cannot reproduce the Python Unicode backfill and
must not silently install an inaccurate search index. Downgrade removes only the
search index/derived column; normal database backup/rollback procedures apply.

## Follow-up order

1. Expose bounded search/read through the bridge and a real picker UI, preserving
   legacy client behavior and Neocities Free constraints.
2. Complete source ownership/remote Git transport/private preview/accept for
   self-service imports. Current operator publication remains supported.
3. Authoring/revisions/author ACL for users without a site; confirm D16/D17 before
   endorsement changes, notifications and social calculations.
4. Public profiles/subscriptions, then explicitly authorized inter-server sync.

Future repository devlogs are tracked separately in [DEVLOG-PLAN](DEVLOG-PLAN.md).
