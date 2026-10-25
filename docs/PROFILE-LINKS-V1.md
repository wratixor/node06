# Account links v1

Source capability: `bilateral_profile_links`. This document describes the
control-only base protocol. Its tokens never authorize private profile access.
Explicit data consent, separate credentials and automatic exchange now extend it
in [PROFILE-SYNC-V1](PROFILE-SYNC-V1.md); old links remain control-only.

## Owner decisions

Separate registration on each server; one-time invitation and explicit confirmation
on both servers; either account may revoke. Future authorized preference exchange
automatically takes fresher per-item changes and retains deletion tombstones.
Passwords, sessions, roles, bans, author trust, votes and influence never transfer.
Remote own posts remain references to original authors/points.

Personal author blocks are local to their server and, independently, to each site.
Neither server blocks nor site blocks enter the profile packet or link protocol.
See [SOCIAL-V1](SOCIAL-V1.md) for the separate site-filter contract.

## User flow and trust boundary

1. Log into registered account A and enter B's canonical public HTTPS origin in
   `/profile-sync/`. A records a 10-minute invitation, owner ID, chosen recipient,
   random state and a server-only random PKCE verifier. The invite secret is shown
   once, in a fragment link to B. It only permits bounded invitation metadata reads.
2. On B, log into an independently registered account. Landing/GET only prefills
   the invitation input and clears the fragment from history. Click **Проверить**;
   B's backend fetches metadata directly from A via pinned verified TLS. No file's
   claimed source, matching handle or parent iframe establishes identity.
3. B displays both origins and the exact A account ID/handle. Explicit B consent
   re-fetches and compares all displayed metadata, then creates a pending code
   bound to both identities, originating request, exact client/redirect, state,
   fixed `node06:link` scope and S256 challenge. The return link is also a fragment.
4. Back on A, submit the response, inspect B's asserted exact account ID/handle,
   then explicitly confirm. A verifies owner/session/state/recipient/expiry and
   exchanges the code server-to-server with its stored verifier. The returned B
   identity and client account must exactly match the displayed pair before A
   records a confirmed link. B cannot use the invitation alone to complete A.
5. Each account lists only its own link records. Either may revoke; private
   settings, local login and authored points are not removed or altered.

The exchange uses the authorization-code binding and **S256 PKCE** construction
from [RFC7636](https://www.rfc-editor.org/rfc/rfc7636), exact client/redirect and
state checks following [OAuth security BCP](https://www.rfc-editor.org/rfc/rfc9700).
It is a narrow NODE06 pairing profile, not a general OAuth/OIDC login server,
SSO, arbitrary-client registration service or existing-session exchange.
No new cryptographic primitives, password exchange or signing claims are added.

## Capability and endpoints

First-party session + exact Origin + CSRF for all mutations:

- `GET /api/v1/me/profile-links`: bounded own list, no credential material.
- `POST .../invite`: `{origin}` returns one-time invitation material.
- `POST .../inspect`: `{origin,id,secret}` reads and validates remote invitation.
- `POST .../approve`: `{invitation,expected}` confirms the exact preview on B.
- `POST .../confirm`: `{origin,id,code,state,peer_user_id,peer_handle}` confirms on A.
- `POST .../{id}/refresh`: check the outbound grant's current peer status.
- `POST .../{id}/revoke`: revoke locally, attempt/retry remote revocation where
  an outbound link-control token exists.

Cookie-independent peer endpoints only accept bounded URL-encoded forms. Origin
headers/browser cookies are rejected, no CORS is enabled, and no token is a login:

| POST `/api/v1/profile-links/…` | Fields | Result |
| --- | --- | --- |
| `metadata` | `secret`, `client_id` | Bound A invitation metadata, no profile |
| `token` | `grant_type=authorization_code`, `code`, `code_verifier`, `client_id`, `redirect_uri` | One-time code exchange; control-only Bearer token and exact pair IDs |
| `status` | `token` | Local grant validity and bound pair IDs |
| `revoke` | `token` | Idempotent `{}`, including unknown/already revoked token |

`redirect_uri` is exactly `<A-origin>/profile-sync/`; token scope is exactly
`node06:link`, lifetime 30 days, with no refresh token. It only checks/revokes that
one link. It cannot read `/me`, private packets, preferences, posts/drafts, change
subscriptions/trust, authenticate a browser or create an account. Future data
exchange requires a separate scoped protocol and consent; linking now grants
none of those data permissions. Both server origins must run this compatible
packet. Nonstandard ports/private-network **peers** are unsupported in v1. A trusted
local management preview may create/cancel records on a developer port; this
does not bypass public-peer HTTPS/DNS restrictions.

## Secrets, limits and failure behavior

All secret, state, code, verifier and token materials have 256 bits; link IDs are UUIDs. Invite/code/grant digests are indexed SHA256;
PKCE uses the RFC S256 challenge, constant-time comparisons and one-time atomic
code consumption. A clears its verifier on success/revocation; expired records
are pruned on later creation as described below. B retains a
grant digest; A must retain its outbound opaque control token to check/revoke B.
That token is sensitive database material, **not encrypted at the application
layer**; existing protected DB/backup access is required. It carries no profile
or session authority. Owner list/file exports never include these values.

All link responses are no-store and frame-denied; the page sets no-referrer and
has only first-party scripts. Secrets travel in fragments/forms, never query
strings, redirects or API request logs generated by this implementation. Do not
configure reverse proxies to log bodies. The page removes incoming fragments
before any explicit inspection/consent. No clipboard reads or browser storage.

At most 100 stored records/account; expired records older than another 30 days
are pruned on new creation. Rate limits: 120 owner operations/hour and 60 peer
requests/IP/minute. Forms are capped at 4 KiB before parsing, peer JSON at 8 KiB;
unknown/duplicate fields are rejected. HTTPS transport resolves all addresses,
rejects any nonpublic answer, pins the chosen IP with hostname-verified TLS,
disables redirects/proxies and permits only the fixed API paths described here and in PROFILE-SYNC-V1. A child-process
deadline covers DNS, connection and response body; shared DB verifier slots bound
concurrency. No configuration flag bypasses these protections.

Distributed status is not falsely atomic: B consumes its code before A can store
its result. A lost response/storage failure never reports A as active; A revokes
its interrupted local record and clears the verifier. If A received a valid
control token before failing/cancellation, it attempts remote revocation and
retains a marked retry on outage. For a completely lost reply, B may retain a control-only
grant with no reachable client token; revoke it on B or let it expire, then make
a new invitation. Codes cannot be replayed to recover access.

Revocation is immediate locally. For an outbound token, A attempts B's idempotent
revocation; on outage it retains a marked retry, not a success claim. B can revoke
its inbound grant immediately; A observes that on **Проверить связь**. An inbound
record cannot push to A because no reverse bearer capability was issued.
Thus a peer's displayed list can be stale until refreshed; a future data worker
must check both local authorization and peer grant validity before every exchange.
The control-only v1 has no profile application. The separately consented data
extension and revocation retry worker are documented in PROFILE-SYNC-V1.

## Validation and rollout

Migrations `0020_profile_links` and `0021_site_author_blocks` precede application
activation through the normal operator backup/migration/deploy pipeline. No new
dependency, server secret setting, production migration or production link is
created by development tests. Existing cookies, user IDs and point IDs are intact.

`test_profile_links.py` uses two separately migrated PostgreSQL schemas and HTTP
apps to check both confirmations, exact identities, PKCE/client/redirect/state,
concurrent code replay, expiry, disabled accounts, either-side revocation, outages,
no social transfer, session/CSRF/embed isolation and no bearer login/profile read.
`test_profile_peer.py` exercises pinned TLS, rebinding/redirect/oversize rejection,
hard deadline and lease cleanup. `test_site_author_blocks.py` covers independent
site/server filters and unchanged shared trust/point reactions/profile packets.
Installed-wheel browser acceptance exercises invitation creation/cancel, no-write
fragment landing, mobile layout and existing private packet export/comparison.

Source checkpoint: full backend345 passed; final focused25 plus local-origin
boundary regression passed; the final protocol rerun16 passed after the last
source-origin fix. Installed-wheel complete HTTPS browser acceptance
and focused profile/invitation/no-write-fragment/mobile acceptance passed.
Backend Ruff/format, JavaScript syntax, graph build61, clipboard/protocol and
Git diff checks passed. Tests use disposable local data; no production profile
or account linkage was read or created. Real public two-server deployment remains
an operator acceptance step after review, not a claim from local fixtures.
