# Private profile packets v1

Source implementation: first-party export and read-only comparison. This is a
foundation for consented profile synchronization, **not** account linking,
authenticated peer transport or an importer. No new migration/dependency.

## User flow

The shared personal navigation links to `/profile-sync/` (Перенос профиля).
After logging in on the trusted origin, download the profile JSON. On another
instance, log in separately, select the file and compare it. Nothing is applied,
no remote URL is fetched and the file never grants authority over its claimed
source account. The source handle/origin are displayed as unverified text.

The file contains private preference lists. It includes six raw color components,
point subscriptions including inactive records and historical revision pins,
favorite point references and references to currently public authored originals.
References retain their source origin/ID/revision/digest. Posts are not copied;
there are no bodies, previews, drafts, subscription static-body snapshots,
passwords, sessions, recovery codes, source proofs, roles, bans, trust edges,
ballots, computed coordinates or influence allocations. Color preference is not
the computed social geometry. Hidden/quarantined/deleted originals do not enter
the public own-point list; saved/subscribed unavailable references remain marked
unavailable with no body. A site hide does not become a server-wide hide.

## API and schema

- `GET /api/v1/me/profile-export`: own packet only, authenticated first-party read.
- `POST /api/v1/me/profile-compare`: packet in request body, first-party session,
  exact Origin and CSRF; returns differences against the current local snapshot.
- Private endpoints reject extra query parameters and are unavailable on embed.
- Responses are no-store, frame-denied and not added to public bridge methods.
- Owner admission: 60 requests/hour. Existing management body cap: 64KiB.

`Packet` in `profile_packet.py` owns the strict schema, published as
[profile-packet-v1.schema.json](schemas/profile-packet-v1.schema.json). `format=node06-profile/1`;
source is a canonical HTTPS origin plus user ID and handle. Lists contain at most
128 references each; complete compact UTF-8 packet is at most60,000 bytes. Export
reads all lists from a repeatable-read transaction. If a list or total byte budget
is exceeded, export returns `PROFILE_PACKET_TOO_LARGE`/413, never a silently
truncated profile. Large-profile pagination remains a later packet.

The packet digest is SHA-256 of sorted-key, compact UTF-8 JSON excluding `digest`.
It detects accidental changes and gives a stable snapshot identifier; anyone
can recompute it. It is **not a signature, identity proof, invitation or grant**.
Strict parsing rejects unknown fields, duplicates, unsupported versions,
invalid six-component values and digest mismatches before comparison.

Comparison returns `verified_identity=false`, `applied=false`, local/incoming
digests, claimed source, color difference and `only_here` / `only_in_file` /
`different` reference lists. References compare by canonical source-origin +
point ID; equal IDs on different servers never collapse. Revision pins,
subscription active state and timestamps participate in differences but do not
authorize votes or act as a last-write-wins policy. No account is looked up by
handle and no local target is resolved from an incoming foreign ID.

Snapshot GET and comparison do not mutate profile, subscriptions or social events;
auth/rate admission still uses existing local metadata. No peer credentials,
network jobs, write grants or transfer of T1 authority are introduced.

## Approved network behavior — 25 October 2026

The owner approved linking two already registered accounts using a short-lived,
one-time invitation with confirmation on both servers. Either account can revoke
the link. Passwords, sessions, roles, bans and influence never transfer.

Within the explicitly authorized data scopes, synchronization automatically takes
the fresher change. Routine changes do not require manual comparison/acceptance.
Own remote posts remain references to originals, without copying authorship or
influence. This supersedes the previously open manual-versus-automatic choice.
The existing file comparison remains a read-only diagnostic, not a sync grant.

These decisions describe the next network implementation; this packet still
neither links accounts nor applies remote data. Its unsigned digest and timestamp
strings are not identity proof or authority to overwrite preferences.

Before peer linking: specify and review a standard authenticated protocol,
explicit scopes/directions, short-lived/replay-bound invitation exchange, revocation,
identity/source proof, origin discovery and SSRF boundaries and credential storage.
Do not turn this unsigned file into a bearer login or automatic merge operation.

The next implementation must track freshness per preference/item, preserve source
provenance and deletion tombstones and make retry idempotent. Import time must not
make an old change fresh. Replayed/offline snapshots must not resurrect removed
subscriptions or favorites. Concurrent equal-time changes need a deterministic
rule; server clock skew and tombstone retention require a documented protocol
policy before automatic application. A whole-profile export timestamp cannot
resolve independent edits. This is implementation work, not an unanswered choice
about whether automatic freshness is wanted.

Cosmetic/device settings, author blocks and external subscription storage still
need their own field contracts. Imported preferences cannot create local trust,
votes or influence. This v1 is not a complete backup/restore or peer sync system.

## Validation

`backend/tests/test_profile_packets.py` checks schema/authority exclusions,
bounds/digests, source-aware comparison, stable own export, hidden originals,
no truncation, unchanged social state, auth/CSRF/Origin and embed isolation.
`NODE06_PROFILE_ONLY=1 .venv/bin/python scripts/check-hosted-browser.py` runs the
installed-wheel HTTPS download/file comparison/mobile/logout acceptance against
a dedicated disposable PostgreSQL database. It is also included in the full
hosted browser driver. No production packet/link is created by these checks.

Checkpoint validation: full backend330 passed, then final profile suite21 passed;
installed-wheel full HTTPS acceptance and focused download/compare/mobile/logout/
embed acceptance passed. The first browser regression expectation was updated
from eight to nine shared personal links, preserving return to the community page
for subsequent color tests. No production private profile was read or downloaded.
