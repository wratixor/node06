# Scoped subscriptions from a static site

Source capability `scoped_embed_subscriptions`, migration0023. The Neocities
point heart is a button, not a link to the community/profile page. Once connected,
it toggles the normal current-version point subscription, uses existing social
idempotency and updates the toolbar/context-menu active state. It does not create
another vote budget. Existing native first-party actions continue to use the
normal management session/CSRF path. A signed-out native action offers an explicit
login link inline instead of navigating to a generic profile.

## Consent and UI

For a static copy without access yet, the first heart click opens a small trusted
management-origin window at its final HTTPS address, without an `about:blank`
redirect. The map shows a connection link and Cancel while waiting. If automatic
opening is blocked, the link retries the same request under a fresh user gesture;
Cancel stops waiting without changing the subscription. The user logs in there if necessary and explicitly
allows that verified site to read/change point subscriptions for15 minutes.
The original action completes on the map after authorization. Connecting to an
already active current-version subscription only restores highlighting; it does
not silently unsubscribe. Later connected clicks toggle normally.

Only subscriptions are delegated. No author trust, favorites, blocks, point
publication/editing, revision ballots, profile lists, roles or site management.
Other external actions keep their existing trusted flows; generic authenticated
full-iframe interaction (`embed_auth`) is not claimed complete by this packet.

The trusted window shows the registered parent origin, current account and scope.
Existing consent can resume for the **remaining** lifetime, without extending it
or silently changing account/session/site. Global logout invalidates its grants.
The account page has **Отозвать доступ сайтов к подпискам** to revoke them
immediately, and the trusted access page can revoke that site's grants. Existing
subscriptions remain after revoking permission; it stops future access/actions.

An available partitioned cookie restores the toolbar state after page reload.
It is Secure/HttpOnly/SameSite=None/Partitioned, host-only, scoped to the site's
subscription API path and expires no later than consent. It is a separate
subscription capability, never the management session. Browsers that deny such
storage retain the capability only in the bridge iframe's memory; reconnecting
needs a user click, and existing consent resumes only until its original expiry.
Unknown state is labelled as needing connection (`aria-pressed=mixed`), not
presented as a known inactive subscription. Focus refreshes visible action state.

## Protocol and least authority

The local SDK/public reads are unchanged. The hidden registered-site bridge adds
five methods, described separately from the anonymous HTTP read-method list:

- `subscription.prepare({state})`: generate an iframe-only256-bit verifier,
  its S256 challenge and a bounded five-minute pending request for the actual
  validated parent. Return the request ID/state and trusted approval URL.
- `subscription.complete({id,state})`: poll through the iframe's verifier until
  the existing native account explicitly approves. Before approval return only
  `{connected:false}`. After approval, exchange once within the same 60-second
  code deadline; the capability stays inside the iframe. No opener is required.
- `subscription.redeem({id,state,code})` (legacy clients): redeem a60-second single-use code with
  the iframe-held verifier. The parent never receives the verifier or bearer.
- `subscription.read({point_id})`: current actor's subscription pin/active state
  only, plus expiry and a domain-separated opaque session/site tag for receipt
  continuity. No account ID, handle, subscriber list or global credential.
- `subscription.set({point_id,subscription,key})`: only the existing native
  subscription operation, with exact revision/digest/active and idempotency key.
  It cannot act as a generic API/method proxy or cast a revision ballot.

A trusted approval page cannot be framed. Its native session, Origin and CSRF
checks authorize approval/resume/revocation. The page checks the existing native server account even if its opener is absent.
Current clients poll the server rendezvous through the iframe-held verifier;
legacy clients may still receive a code via their exact opener origin and forward
it to the exact bridge window. Message transports bind source/origin/channel;
completion binds state/request ID and the iframe-only S256 proof. Codes are bound to exact site/parent/user/session and S256 verifier; replay fails.
Nested outer parents cannot request private bridge operations. Popup denial or
cancellation never changes a subscription or navigates to a generic profile.

Bearer credentials stay inside the iframe, optionally in its HttpOnly partitioned
cookie. They never enter URLs, parent DOM/storage or public read envelopes.
Management cookies are never accepted as subscription authorization. Cookie
operations require the embed Origin; bearer calls reject unrelated cookies and
foreign Origins. The bridge itself uses same-origin API requests; static parents
need no cross-origin fetch permission or third-party management cookie access.
The same-origin deployment case omits cookies and uses memory instead.

The backend rechecks active account, unrevoked/unexpired issuing session,
15-minute expiry, current active site and exact primary origin on every read/write.
Point reads and mutations use the site's normal visibility/purge rules. Social
writes reuse graph locking, revision validation, proposal gates, idempotency,
local influence budgets and preference-change capture. No raw session credential
is stored by this new grant table; only the native session digest reference and
hashes of one-use codes/bearers. These remain protected database/backup data.
A compromised explicitly authorized parent can exercise this narrow subscription
scope until expiry/revocation; consent does not make arbitrary parent code trusted
for any other account action.

## Routes and bounds

Embed-origin JSON POST routes under
`/bridge/v1/{site}/subscriptions/{prepare,complete,redeem,read,set}` are separate from the
anonymous `/read` method allowlist. Forms are not accepted; unknown
fields, wrong pins, wrong site/origin, replay and privilege expansion fail.
Bodies are capped at4KiB. Limits:30 prepare requests/IP/minute,240 peer calls/IP/
minute,240 grant reads/writes/account/minute,1000 pending requests/site. Writes
also share native240/account/hour and480/IP/hour social limits. Expired pending/
grant records are cleaned on preparation after a day; stale records never extend
consent or restore a revoked token.

Management-origin routes `/embed-subscriptions/{request}/` and
`/{info,approve,resume,revoke}` are private no-store/frame-denied pages/actions.
`POST /api/v1/me/embed-subscriptions/revoke` requires the normal own session/CSRF
and revokes all the caller's grants. No private grant listing is public. Request
IDs/state in URLs are not bearer credentials; codes, verifiers and tokens stay
in bounded POST bodies/Authorization headers. Keep those out of proxy logs.

## Tests and rollout

`test_embed_subscriptions.py` exercises real PostgreSQL consent, PKCE/state/site/
origin binding, concurrent code replay, pins/idempotency, cookie/memory paths,
logout/disabled/expiry/site-change denial, revocation, native-session isolation
and unchanged author trust. Migration0023 upgrades online through psycopg; normal
migration roundtrip suites also cover removal before0022/older downgrades.

`check-embed-subscriptions.cjs` runs through the installed-wheel HTTPS fixture,
actual static HTML/assets and actual cross-origin bridge, under self-only parent
connect CSP. It covers direct toggling, highlighted panel/menu/reload, consent,
revocation, denied cookie storage and remaining-lifetime resume. Local-network
access permission is only a Chromium fixture requirement for mocked .localhost
parents, not a production permission/configuration switch.

Deploy engine/migration0023 through the normal reviewed pipeline, then publish
the static assets (the existing main Neocities workflow). No new operator secret,
dependency or site registration is needed. If static publishing finishes before
the server upgrade, reconnect/reload after both complete. Source delivery is not
production deployment. A downgrade drops grants/requests while retaining accounts
and actual subscriptions; an old client cannot reuse a dropped capability.

Source validation checkpoint: full disposable PostgreSQL suite380 passed; focused
auth/public/subscription suite37 passed; final grant suite14 passed, including
malformed-origin rejection and populated0023 downgrade/re-upgrade preserving
actual subscriptions. Installed-wheel full HTTPS acceptance and focused real
static-parent/bridge acceptance passed, including denied cookie storage, resume,
revocation and inline guest login. Backend Ruff/format, build61, JS syntax and
clipboard/protocol checks passed. No production deployment or account operation.

## Popup compatibility follow-up — 26 October 2026

The published Neocities assets and server capability were verified as current
(server build `249f41d`). In the owner's in-app browser, clicking the disconnected
heart left it pending without a visible connection window. The prior flow opened
`about:blank` synchronously and replaced its location after preparing the request.
The follow-up opens the final trusted URL directly and keeps an explicit retry
link and Cancel visible. Source-window/origin/state/PKCE checks are unchanged;
no additional authority or migration is introduced.

The installed-wheel HTTPS/static browser acceptance now rejects blank-window
launches, simulates a blocked initial open, retries through the visible link,
checks consent/toggles/highlights/reload/menu, denied cookies/resume/revocation,
and cancels another blocked attempt without leaving the action disabled.
Protocol/clipboard checks, JS syntax, build 61 and diff checks passed. This is
source validation; the updated assets have not been published to Neocities yet.

## Common account and detached tabs — 26 October 2026

An account remains shared by every site attached to one server/database. The
15-minute site grant is a narrow transport permission, not a separate account,
registration or subscription store. The approval page identifies the already
signed-in server account and hides redundant login controls.

The reported page text pinpointed a detached opener: the previous UI skipped
checking the session when `window.opener` was absent. Checking/approving now
works in an ordinary top-level tab. The map polls `subscription.complete` every
2.5 seconds for at most five minutes, using the bridge's original verifier. Only
an explicitly approved, active native session/site may complete; stale/revoked,
wrong-proof/state/site and already-exchanged requests fail. The bearer stays in
the bridge and follows the existing expiry/revocation rules. Old code-return
clients remain supported. No migration, cookie-domain expansion or new account.
Server and static assets must both update before this path can work live.
