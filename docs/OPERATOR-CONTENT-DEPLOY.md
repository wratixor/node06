# Operator deployment of public site content

This is an operator-selected release path, separate from the planned self-service
GitHub source challenge, private preview/accept and remote import API. A site
registration already exists. Do not register it again or copy the engine into
the content repository. Within one instance the DB, accounts and graph stay shared.

## Implemented boundary

Migration `0005_operator_roots` adds source bindings and imported point metadata.
`python -m node06_service.root_publish` reads only manifest-listed blobs from one
immutable commit in a trusted operator-created bare Git repository. Origin must
match the selected public repository and commit must equal the fetched
`refs/remotes/origin/main`. Existing P04a limits/UTF-8/mode/link validation applies.
No checkout, hooks, content scripts, templates or dependency installation occurs.

The privileged deployment config explicitly selects the repository, active site
ID and exact verified site origin. This OS-level authority is **not** a proof of
GitHub ownership, an authenticated site-owner API call or a new account. Events
record `operator_roots_published` with a null user actor and source provenance.
The registered owner's ID is pinned on first acceptance; owner/origin/repository
changes, inactive entries, disabled owners, welcome ownership changes and unexpected
point-revision changes fail closed. A manual transfer/unbinding procedure is not
implemented; never delete rows to force a new binding.

A single transaction stores source SHA/digest, immutable Markdown revisions,
source edge claims and the existing welcome's `welcome_source=git`. New IDs are
site-scoped; collisions cannot overwrite unrelated points. The initial switch
from the UI welcome is explicit operator acceptance through this config. UI
welcome editing then correctly refuses to overwrite Git content.

Same candidate is a no-op. A new SHA with identical meaning does not create
point revisions. Removed points become retired with revisions retained;
reintroduction restores the same identity. Releasing source claims preserves
other edge claims and points. No destructive database cleanup occurs.

Public hosted and full-iframe graphs project accepted active roots, links,
languages and public source URL/SHA. Markdown is escaped, safe links are rendered,
code stays literal; raw HTML cannot execute. Display-only coordinates do not
pretend to represent votes. RU/EN remain distinct points in the shared graph.
Revoking a site hides its roots. The existing public bridge uses this same graph.

External `md://point/` revision citations are deliberately rejected by this
operator path until trusted public revision indexing/pin persistence is ready.
Self-service imports, user point editing, voting, support reconfirmation and
notifications are still unfinished. This release does not claim their acceptance.

## Deployment contract

See `geno-dice-deploy/docs/NODE06_DEPLOYMENT.md` for the owner-run commands.
The optional root-owned `node06-content.conf` pins the wiki binding and opts into
publication on the explicit NODE06 deployment. Check-only resolves public main and
checks application capability; it does not migrate or import. The real release
backs up the DB before migration/publication and runs the publisher with the
private environment through systemd. No secrets are shell-sourced or printed.

With content enabled, app SHA alone never decides whether publication is needed:
content updates are processed even when application code is unchanged. It writes the
existing site ID into generated `build.env` as the default hosted entrance,
restarts only NODE06 and verifies accepted content SHA in the public graph before
recording success. The iframe IDs/URLs remain unchanged. Removing the opt-in file
does not remove published points or unbind the source.

The deployment toolkit's opt-in autodeploy extension adds a combined successful
release receipt (engine/content SHAs, source binding and configuration/environment
hashes). With that reviewed toolkit installed, unchanged releases only check public
readiness/build/embed/content and repair runtime modes; they do not backup, build,
publish or restart. Changed inputs/missing receipt/inactive service take the normal
backup-first path. Before that extension is installed, content opt-in still forces
the full release on each run. The first receipt requires one successful full release.

`node06-deploy.timer` is installed disabled and, after explicit owner activation,
polls main of the configured engine and content sources five minutes after each
run. It uses the same host lock; no webhook secret or public inbound deploy endpoint
is required. It never updates the root toolkit itself. Review/promotion/install,
activation, journal checks and stop/recovery steps belong to the deployment
repository's `docs/NODE06_DEPLOYMENT.md`. This application documentation does not
confirm installation or activation on production. Future devlogs follow this
operator contract rather than encouraging manual edits to installed scripts.

On failure before commit the prior graph remains intact. A failed health check
after commit may leave the new content installed; rerun safely or publish a
reviewed content revert through main. A DB restore/downgrade is never automatic.
The application's earlier revision must not be installed against an incompatible
schema without reviewing migrations and preserving accounts/revisions.

## Local validation

Use the full PostgreSQL pytest suite and Ruff as documented in `backend/README.md`.
New fixtures cover dry-run, no-op, revisions, retirement/reintroduction, source and
owner binding, collisions, rollback, safe rendering, hosted/embed projection and
online migration downgrade/upgrade on disposable PostgreSQL using psycopg.


Git-owned home blocks and per-site priority extend this release path through
migration 0007. See [HOME-BLOCKS-V1](HOME-BLOCKS-V1.md) for manifest data, source
selection, migration preservation and application-before-content merge order.
