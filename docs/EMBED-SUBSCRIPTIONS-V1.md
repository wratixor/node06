# Shared server login for static-site subscriptions

Capability `scoped_embed_subscriptions`, existing migration `0023_embed_subscriptions`.
One database/server has one account and subscription store across all its sites.
An active registered site uses that existing login automatically. There is no
per-site Allow step or independent 15-minute connection period. This policy
supersedes the earlier consent-based transport after the owner's correction on
26 October 2026.

## User behavior

The point heart toggles the ordinary current-version subscription and updates
panel/context-menu highlighting. A previously subscribed point remains subscribed
when its session is first recognized. Later clicks toggle normally. A native
signed-out action offers login, not a generic profile navigation.

A static copy first tries its existing bridge session. When none is available,
the first action opens a short trusted management-origin login handoff. An
already signed-in account is recognized and the handoff completes automatically,
without permission buttons. Only a signed-out user needs normal server login.
The account page has ordinary local/global logout; no site subscription-permission
settings are required.

One PKCE request may be prepared per disconnected static document so its actual
HTTPS handoff URL can open synchronously in the click gesture. Preparation alone
has no account authority and changes no subscription. A four-minute client cache
fits inside the five-minute request deadline. A blocked popup offers an explicit
login retry link and Cancel rather than a disabled unexplained heart.

A browser may isolate cross-domain cookies, sever `window.opener`, or refuse to
close a detached tab programmatically. The server handoff works without an
opener, and the map completes through the original iframe's proof. If storage is
denied, the iframe retains its session in memory; reloading may require another
automatic handoff on the next action. This is a browser constraint, not a second
registration or permission setting. No successful silent cross-domain login is
claimed where the browser makes the native session inaccessible.

## Session and transport scope

New bridge credentials expire at the issuing native session's expiry, not after
15 minutes. Every operation still checks that native session: local/global
logout, recovery, disabled accounts, inactive sites, changed primary origins,
expiry and revocation invalidate it. The optional Secure/HttpOnly/SameSite=None/
Partitioned cookie is host-only and scoped to the site's bridge API path. Native
session cookies and passwords never enter a third-party parent or shared domain.

The current delegated transport remains limited to point subscriptions. An
active site registration is the server's trust boundary for this automatic
transport. It grants no author trust, profile lists, favorites, blocks, publication,
editing, revision ballot, roles or generic proxy. Other actions retain their
existing trusted-server flows; general full-iframe auth remains separate.

The management-origin top-level handoff checks the native login and performs
its internal `/approve` POST with normal Origin/session/CSRF checks. There is no
interactive approval UI. The legacy DB field `consented` remains an internal
issued-session marker; this update does not need a migration. Legacy code-return,
info/resume/revoke APIs remain compatible; direct revocation invalidates already
issued credentials, while a later authenticated action may establish a new one.

## Protocol

The anonymous public-read methods are unchanged. Separate bridge methods are:

- `subscription.prepare({state})`: make an iframe-only 256-bit verifier, S256
  challenge and five-minute request bound to the registered site/actual parent.
  Return request ID/state and the trusted HTTPS handoff URL.
- `subscription.complete({id,state})`: poll with the iframe-held verifier every
  2.5 seconds, for at most five minutes. Pending responses reveal only
  `{connected:false}`. After native authentication, exchange once within the
  60-second code deadline. The bearer remains inside the iframe.
- `subscription.redeem({id,state,code})`: legacy one-use code exchange with the
  same iframe-held proof and server session bindings.
- `subscription.read({point_id})`: only the subscription pin/active state, expiry
  and domain-separated opaque native-session/site tag for receipt continuity.
- `subscription.set({point_id,subscription,key})`: existing pinned/idempotent
  native subscription mutation; no generic proxy or revision ballot.

The trusted handoff cannot be framed. Parent/bridge messages validate source,
origin, channel and exact schema. Completion binds request/state/site/parent and
S256 proof; foreign proofs, stale requests, revoked sessions and replay fail.
Public parent DOM/storage/URLs never contain reusable bearers or native session
credentials. Unknown subscription state is `aria-pressed=mixed` until recognition.

## API bounds and deployment

Embed-only JSON POST routes live at
`/bridge/v1/{site}/subscriptions/{prepare,complete,redeem,read,set}`. Native
management cookies are not accepted there; cookie calls require embed Origin,
while bearer calls reject foreign Origins/unrelated cookies. Bodies are bounded
at 4 KiB, unknown fields are rejected, and site visibility/purge rules apply.
Rate limits remain 30 prepare/IP/minute, 240 peer/IP/minute, 240 grant/account/
minute, 1000 pending requests/site; writes share native 240/account/hour and
480/IP/hour limits. Expired requests/grants are cleaned during preparation.

Deploy both server and static assets. No new secret, registration, dependency,
CSRF exemption, cookie-domain expansion or migration is needed. Existing narrow
credentials retain their stored deadline until an automatic native-session
handoff replaces them. Source delivery does not establish production rollout.

Regression checks use disposable PostgreSQL and an installed-wheel HTTPS/static
fixture. They cover shared native account identity, no permission click, session
expiry, exact proof/state/site, replay/concurrency, logout/revoke, panel/menu/
reload highlighting, denied storage, detached openers, blocked popup retry and
cancellation. See `scripts/check-embed-subscriptions.cjs` and backend tests.

Validation for this policy: 59 subscription/auth/hosted PostgreSQL tests plus a
separate two-registered-sites shared-account/logout test passed. Installed-wheel
HTTPS acceptance completed with zero permission clicks, including detached
openers, denied storage, reload/menu state, retries and cancellation. Ruff/format,
JS syntax, protocol/clipboard, build 61 and diff checks passed. No production
publication or account action was performed.
