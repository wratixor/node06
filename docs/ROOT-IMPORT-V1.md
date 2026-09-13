# NODE06 site roots and GitHub fork import v1

Status: target contract, not implemented. Requested 13 September 2026.
See [IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md) and [API-V1.md](API-V1.md).

## 1. Why forks are useful

A site owner may fork NODE06 for its static client and author extra Markdown
roots in Git. The shared service imports selected data into the same graph.
Forking is optional: the full iframe and welcome editor need no Git knowledge.
No database fork, independent user system or separate meaning-space is created.

A fork is not automatically a registered site. First establish service account,
verified site origin and site ID; then attach the public GitHub source through
an owner-managed preview flow. Repo control and website control are separate
proofs. Site visitors remain ordinary service users, not repo collaborators.

## 2. Site and repository claims

Site claim: generate unpredictable short-lived proof, store its digest, request
that owner upload a fixed filename such as `/node06-verification.txt` containing
version/site/nonce. Fetch only this exact path on the claimed HTTPS origin,
max8KiB/5s, no credentials. Reject private/link-local/loopback/reserved addresses
and alternate schemes; verify all DNS answers and the actual connection target,
TLS hostname and redirect chain. MVP redirects off claimed origin are rejected.
Rate-limit attempts; single-use acceptance; reverify on change/transfer/expiry.

This is an explicit narrow exception to “no URL fetch”: it is not an endpoint
for retrieving arbitrary user URLs. Untrusted response text is data, not
instructions. Neocities origin belongs to the whole subdomain, not one path.
Custom alias requires another proof; hostname/IDNA/port normalization must have
fixtures. Origin possession does not grant rights to some other site account.

Repo claim: owner registers `owner/repository`, branch and bounded subtree,
then commits a service challenge into the manifest. Service verifies the
challenge at a resolved immutable commit. GitHub public API only, not arbitrary
Git hosts/URLs. Scope public repos first; no personal access tokens stored in
Neocities, embed snippets, browser JS or repository. Private repo integration
would need a separate authorization model and is deferred.

## 3. Manifest sketch

Exact JSON Schema must be published in P04 before importer implementation.
Example is illustrative and not a live configuration:

```json
{
  "schema_version": 1,
  "site_id": "s_0123456789abcdef0123456789abcdef",
  "content_directory": "site-content",
  "welcome": {"file": "welcome.md", "mode": "git"},
  "points": [
    {"id": "garden", "file": "garden.md", "lang": "en"},
    {"id": "sad", "file": "sad.md", "lang": "ru"}
  ]
}
```

`garden` and `sad` are independent local identities. `lang` describes content,
not an equivalence relation. Global IDs become
`r_<site_uuid32>_garden` and `r_<site_uuid32>_sad`. Existing core slugs remain
reserved. Welcome resolves to the existing site point `s_<uuid32>`, never a
second `r_..._welcome` point. File rename leaves explicit stable local ID intact.

`site_id` in a manifest cannot claim a site: association requires authenticated
site owner, verified origin and source proof. Challenge fields are separate
verification metadata, absent from generated public UI except the proof file.
Changes of repo/ref/subtree are owner actions with audit and revalidation.

The fork's copied `content/` is not imported as fresh roots. Only manifest-listed
files under site-content, including optional welcome, participate. Namespaced
ID allocation is server-side; manifest cannot provide arbitrary global ID or
replace `all-sites`, another site's welcome or another user's point.

## 4. Links without graph isolation

Proposed explicit syntax for imported files:

```markdown
[local thought](md://local/garden)
[core](md://point/observation-ru)
[another site](md://point/s_0123456789abcdef0123456789abcdef)
```

Legacy core `md://slug` remains compatible in the original core builder. New
site import grammar has no ambiguous “local first, maybe global” lookup.
The importer resolves local IDs before validation; external point IDs must
exist publicly at commit time. One external relation is semantically symmetric,
without writing into another owner's file. A reverse backlink is dynamic API
state. Within the same import source, reciprocal local links are required.

Each edge has one canonical pair and separate provenance claims. Removing a
link from one source releases that source claim only. It cannot remove another
source's claim or an independently authored dynamic edge. Reactions attach to
points, not duplicate claims. External link quota helps prevent hub spam.
Core static fallback cannot show every new backlink while offline; API enriches
it, rather than rewriting core Git on every import.

A normal user cannot connect arbitrary old points via an import disguise:
source ownership limits mutations to that source's roots/welcome. Owner-managed
Git root topology may evolve through versioned source edits, just as authors
may edit references on their own DB points. Proposed source-local disconnected points generate a warning; a new
site normally links welcome to its roots for discovery. Never delete an
intentional orphan solely because it lacks neighbours.

Meaning-bearing word links also pin a target revision. The import preview
resolves their current revisions and shows them for acceptance; an optional
per-point `link_revisions` map may explicitly cite an accessible historical
version. Persist accepted pins with the imported point revision, not only the
working branch. If a selected current target changes before accept, refresh the
preview or explicitly accept its old version; never silently substitute text.
Unchanged imports reuse existing citation pins, avoiding meaningless revisions.

## 5. Import pipeline

1. Resolve registered branch to immutable SHA using bounded GitHub requests.
2. Read manifest + allowlisted blobs from the same SHA. No mixing branch reads.
   Enforce total files/bytes/depth and GitHub rate limits with ETag/backoff.
3. Reject symlinks/submodules/LFS pointers/path traversal/absolute paths,
   archive bombs/binary content/unknown schemas/invalid UTF8. Prefer blob reads
   over extracting arbitrary tar archives. Never execute build.py, hooks,
   JavaScript, workflows, shell, templates, package scripts or YAML constructors.
4. Parse Markdown through the same safe content boundary as user points;
   raw HTML/scripts blocked. Validate IDs, revision hashes, links, stable dates,
   source ownership and quotas; report readable filename/line errors.
5. Produce candidate diff: added/edited/retired points, changed edges, welcome
   change, pending-support consequences, resource delta. Preview is authenticated
   owner state, not public graph content.
6. Owner accepts exact candidate SHA+digest. Recheck owner/source config revision,
   quotas and external target existence. If anything changed, conflict/re-preview.
7. In one transaction store revisions/edge claims/source pointer/events and mark
   affected endorsements pending. Last-good source stays active on failure.
8. Return immutable import operation ID and accepted revision. Same SHA+config
   repeat is no-op; retry after timeout uses the same operation key.

Initial mode: manual preview/accept on trusted management UI. Polling may prepare
candidates later; automatic publication of source changes must be an explicit
owner source setting, with quotas, revocation and notification semantics intact.
No public GitHub webhook endpoint required for MVP. If added later, verify
signatures, dedupe deliveries and still pin commit/read data only.

## 6. Editing, notices and source authority

Git roots and Git welcome are edited in their connected repository; import
creates a new content revision. Ordinary authored point/UI welcome edits use
HTTP revision control. One active writer per point: UI cannot silently override
Git source, and a later Git import cannot silently overwrite an UI-owned welcome.
Switching source requires preview/explicit owner action, history retained.

Support/opposition refers to a content revision, not unconditional future text.
Material import edits use the same change-notice/pending-reconfirmation rules
as interactive edits (API-V1). A bulk import may change many supported points;
notifications group by source/run but preserve per-point before/after and
individual reaffirm/remove actions. No bulk automatic reaffirmation.

Inbound links from other authors do not change the recipient's meaning revision;
otherwise any third-party mention could freeze its endorsements. Author-owned
body/outgoing source link changes do. Theme/layout/timestamps/import no-op do not.

Deletion proposal: file absent from manifest becomes a previewed retirement;
keep stable tombstone/revisions/backlinks and user content unless a separately
approved retention/moderation action redacts it. A source outage, force-push or
404 never silently deletes accepted roots. Reverting source to an earlier SHA
still creates a new accepted revision event; it does not secretly reactivate
previous endorsements.

Repo/source/domain transfer pauses writes/imports until owner reverify. Public
IDs survive, author/provenance history is not rewritten to the new owner.
Removing a fork connection is not permission to erase global discussions.

## 7. Delivery and quotas

Service build artifacts are from our reviewed repository revision only.
A fork can build/deploy its own Neocities frontend in its own GitHub Actions,
with its own deployment credential; our service never sees that credential.
Fork users pin a supported SDK/protocol version and receive upgrade guidance.
No user DB/events/sessions or raw confidential lore is committed to any fork.

Initial proposal: <=100 roots/site, <=1MiB text/source, <=32KiB text/file,
<=16 declared links/point, one import/site at a time, >=15min accepted import
interval. Shared operator ceilings also limit total import concurrency/cost.
Review numeric quotas after measurements; reserved quota is transactional and
failed candidates release reservations. No-op pulls don't change point activity.

Credits/license/provenance are explicit at source registration. The repo's code
license does not automatically license every external user's Markdown under it.
Owners attest rights and choose a supported content license; do not scrape or
relicense third-party material. Canonical lore roots are selected public sources,
never an automatic import of the internal shared-context repository.

## 8. Acceptance matrix

Two forks reuse a local slug -> different stable roots; links across forks and
core resolve in shared graph; copied core is not duplicated; same SHA no-op;
rename file stable ID; cross-source edge claim survives removal by other source;
missing target/partial candidate rolls back; all-sites protected; welcomed source
switch explicit; git update notifies supporters and makes old support pending;
unsafe Markdown/SSRF/path traversal/symlink/oversize rejected; GitHub outage keeps
last-good; revoke owner cannot import; quota race bounded; own export has no
foreign private data; forum discussion is not deleted with source retirement.
