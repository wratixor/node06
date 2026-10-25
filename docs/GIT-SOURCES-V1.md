# Owner-managed GitHub sources

Implemented source packet 25 October 2026. Requires Alembic `0019_git_sources`.
This is separate from operator-selected content deployment and from deployment
of the engine itself. No source fork, workflow, build script or user JavaScript
is executed by this service.

## Owner flow

On «Мои сайты», open an active verified site and «Корни из GitHub».

1. Enter public `owner/repository`, branch, update policy and confirm publication
   rights. The server issues a 256-bit `source_proof`, shown once. Commit that
   field into the repository's root `node06-roots.json`, alongside the existing
   manifest fields. The site ID must match the registered site.
2. Request a preview. The server validates repository control, fetches one
   immutable commit, validates the manifest and shows before/after text plus
   retirements privately. Public roots have not changed yet.
3. Explicitly accept the preview and Git management of the welcome. It expires
   after 30 minutes. A changed site/source/revision requires a fresh preview.
   A lost response can be retried with the same preview ID without another
   publication. Refreshing the page recovers the accepted state.
4. Manual is the initial policy. Opting into automatic updates activates polling
   only after the first explicit acceptance. It checks approximately every 15
   minutes; switching back to manual pauses future automatic acceptance. Network,
   quota and validation failures preserve the last accepted roots and record a
   stable error. A source outage never retires roots.

The challenge expires in one hour. Only its digest is stored. Losing it requires
reissuing confirmation; this invalidates old previews and pauses polling until
another explicit acceptance. Repo ID and repo-owner ID are pinned at verification
and checked on each fetch. Transfers/renames require renewed owner confirmation.
An already accepted source cannot be silently rebound to another repository URL.

Existing sources published by deployment remain operator-managed. Their deployed
update policy continues; the web UI does not adopt their authority just because
the visitor controls a site. This packet introduces no PAT/OAuth credentials.
Private repositories, arbitrary Git hosts, disconnect/ownership transfer and
external revision-pin imports remain outside this first self-service packet.
The supported content format matches the existing operator importer: local
manifest roots/welcome, home blocks and safe inline links. Do not copy upstream
core content into a site's namespace. See [manifest contract](ROOT-PREFLIGHT-V1.md).

## Security and atomicity

All source endpoints require a real first-party session, exact site ownership,
CSRF/Origin checks for writes and an active owner/site binding. They are excluded
from the embed origin, public bridge and third-party parent. Neither a public
manifest nor its `site_id` grants publication rights. Preview bodies are private.
The API requires an explicit rights attestation; importing does not change the
content's license or transfer copyright.

The source configuration has a generation token. It binds proof, repository,
branch, origin and owner. IO occurs outside the graph lock. Both after fetch and
inside accept the service rechecks authorization, bans, generation, origin,
settings revision and accepted root pointers. Publication uses the same atomic
publisher as operator deployment, including protected source IDs, provenance
claims, Git support transfers and permanent-purge guards. Concurrent acceptance
returns the same receipt. Manual preview never publishes automatically.

GitHub reads use only `api.github.com`, pinned public DNS addresses, TLS hostname
verification, fixed generated API paths and no redirects, credentials or proxy
URLs from the repository. Repository/ref/tree/blob objects are resolved to a
commit, regular-file modes are required and blob sizes/Git SHA-1s are checked.
Symlinks, submodules, truncated trees, arbitrary URLs and oversized responses
are rejected. No clone, archive extraction, checkout, hooks or workflow execution.
Transport references: [Git refs](https://docs.github.com/en/rest/git/refs),
[Git trees](https://docs.github.com/en/rest/git/trees),
[Git blobs](https://docs.github.com/en/rest/git/blobs).

A child process has a 30-second total deadline, including DNS and body reads.
The existing distributed verifier leases also bound concurrent downloads across
API/worker processes. There are at most 128 API requests per snapshot and 3000
entries per nonrecursive tree; normal manifest/file/source ceilings still apply.
Unchanged automatic pulls read only repo identity and branch ref, without loading
bodies or changing activity. Anonymous GitHub API quota is shared by the server;
quota errors defer the next check instead of weakening validation.

Each site retains at most one bounded preview. Expired previews are excluded from
status and cleared by the worker. Thirty-day point cleanup also clears previews
containing that point; purging the entrance stops its polling. Retired roots and
independent discussions keep the existing operator-import semantics.

## API

Owner-only routes under `/api/v1/sites/{site_id}/source`:

| Method | Suffix | Action |
| --- | --- | --- |
| GET | empty | Configuration, stable error and private preview |
| PUT | empty | Configure/renew challenge with expected_generation and rights_confirmed |
| POST | /preview | Download and persist private preview for generation |
| POST | /accept | Accept generation/preview_id and accept_git_welcome=true |
| PUT | /policy | Set manual/auto for generation |

Configuration/accept are optimistic and fail closed on stale state. Body/nonce/
network exception text is not logged or returned in error responses. Source
mutations are owner-rate-limited; fetch attempts have a one-minute per-site
cooldown. Normal source/policy/publication metadata is audited without the nonce.

## Operation and rollback

Normal reviewed deployment stops the old service, installs the updated package,
runs `alembic upgrade head` and restarts it. No additional systemd timer or secret
is needed. A separate bounded worker checks at most one due source per minute,
independently of social calculations. `/api/v1/meta` advertises `owner_git_sources`
and reports source-worker health; per-source errors appear in its owner view.

Before a downgrade, stop the new service. Downgrading 0019 drops private source
configuration/previews and stops their polling; accepted roots/revisions are
preserved and become operator-managed on a later upgrade. Never run this binary
against a schema below 0019. The permanent 0018 tombstone rollback boundary still
applies. Independent Neocities engine deployment is unchanged.

## Acceptance

Disposable PostgreSQL tests cover proof/expiry, owner loss during IO, stale
previews, simultaneous acceptance, receipts, manual/auto polling, errors and
purged previews. Deterministic GitHub fixtures cover object hashes/modes, private
repos, malformed refs, request budgets and unchanged commits. Installed-wheel
HTTPS acceptance uses a clearly isolated synthetic Git loader for UI checks;
transport is checked separately, including a read-only real public-repository
smoke check. These tests do not connect a production source or deploy a server.

Verified 25 October: full backend run 292 passed; the final focused source/transport
checks additionally cover the unchanged-commit optimization, populated0018↔0019
rollback and private cache headers. Online PostgreSQL/psycopg migrations, installed-
wheel HTTPS full browser acceptance, isolated owner-source mobile/lost-response
acceptance, static 51-root navigation, Ruff/format, build, protocol and clipboard
checks passed. A read-only child-process smoke fetched all 5 public wiki roots
at `851b16df81a58577188aba61950ad8be6a25f46b`; it performed no registration,
publication or deployment. Source UI browser data is explicitly synthetic, not a
production repository challenge or remote write acceptance.
