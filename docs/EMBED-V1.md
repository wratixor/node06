# NODE06 embedding protocol v1 — target contract

Status: proposed implementation contract, not deployed. Owner selected bridge
and full iframe on 13 September 2026. Architecture and work packets:
[IMPLEMENTATION-PLAN.md](IMPLEMENTATION-PLAN.md). HTTP: [API-V1.md](API-V1.md).

## 1. One service, three clients

- Hosted standalone wiki: full UI on the Amsterdam service origin.
- Full iframe: same UI starts at the embedding site's `s_<uuid>` point.
- Local UI + bridge: HTML/CSS/UI stays with the site owner; a small external
  HTML document handles same-origin API requests and returns typed messages.

All three address the same points/users/revisions/votes. Sites are registrations
and entry points, not accounts, extra voters or isolated content databases.
One user can own several sites; owning a site does not own its visitors' points.

Routes are planned, not currently available:

```text
<embed-origin>/bridge/v1/<site_id>/
<embed-origin>/embed/v1/<site_id>/?p=<optional_shared_point_id>
<service-origin>/sites/<site_id>/?p=<optional_shared_point_id>
<service-origin>/p/<point_id>/
<auth-origin>/                 trusted top-level login/management
```

`site_id` is public configuration identity, not a credential. Default center is
that site point; an explicit valid public `p` overrides it. Home goes to the
site point, All sites to the shared core `all-sites`. Opening another site's
point stays in the current shell/theme until an explicit external navigation.

## 2. Origin registration and embedding policy

Any HTTPS site may connect after site registration/proof; Neocities Free is the
first tested target. This does not promise compatibility with hosts that block
external frames/scripts. No wildcard `*.neocities.org` grants over user state.

Site registry owns a set of individually verified origins. Scheme/hostname/port
are compared after URL normalization, never suffix matching. HTTP localhost is
an explicit dev-only allowlist. Null/opaque/file origins are rejected for writes.
Path is not an origin boundary: two independent tenants sharing one hostname
cannot be separated by origin verification alone; MVP supports host-level owners.

Bridge/full per-site responses use route-specific `frame-ancestors` allowing
only registered exact parent origins. All ancestors must satisfy policy: nested
embedding is not automatically supported. Management/login pages use
`frame-ancestors 'none'`. Avoid a blanket X-Frame-Options DENY on embed routes.
Cache keys must include site config/origin-policy revision. Revoking an origin
invalidates grants and subsequent API operations, not just new iframe loads.

Generic public read-only embedding on an unregistered origin can be introduced
as a separately labelled mode: it does not create a new site point, claim a
site or gain authenticated bridge commands. MVP onboarding verifies the site.

## 3. Bootstrap and message envelope

Both documents establish a fresh channel per iframe instance. Suggested flow:

1. Parent loads a pinned-major SDK and external iframe URL with public site ID.
2. Parent generates random channel nonce and posts `hello` to exact embed origin.
3. Child checks `event.source === window.parent`, observed `event.origin` against
   its site registry and envelope size/schema; binds channel to that source and
   origin. It ignores a claimed `parent_origin` inside the payload.
4. Child replies `ready` to that exact origin with protocol version, capabilities,
   public config revision and channel nonce. Parent checks source is precisely
   `iframe.contentWindow`, origin, protocol and nonce.
5. Every later message repeats version/channel/request ID. A navigated/reloaded
   iframe requires a new handshake. Pending requests fail; they cannot attach
   to a new site/actor silently.

```json
{
  "protocol": "node06-embed/1",
  "channel": "random-instance-nonce",
  "id": "client-request-id",
  "kind": "request",
  "method": "point.get",
  "params": {"point_id": "s_example"}
}
```

The example ID is illustrative. `result` and `error` responses match id/channel;
errors contain stable code and request_id, not stack traces. Use structured
clone plain records only, strict schema, unknown fields/method rejection.
Never use `eval`, deserialize executable code or return arbitrary API HTML.

Nonce is channel correlation, not authorization. The parent host controls its
own JavaScript, can observe its messages and can issue allowed commands. Origin
proof is not proof that the website is benevolent.

## 4. Allowed commands and limits

Public: `site.get`, `point.get`, `field.get`, `neighbors.list`, `feed.list`,
`points.search`, `capabilities.get`. UI: `theme.set`, `navigate` and safe layout
settings. Child events: `ready`, `point.changed`, `resize`, `auth.state` without
credentials, `upgrade.required`. Parent never supplies arbitrary fetch URL,
HTTP headers, SQL filter, HTTP method or token audience.

Writes are intents, not automatic forwarding with a global session:
`point.createIntent`, `point.editIntent`, `reaction.setIntent`,
`reaction.clearIntent`, `trust.setIntent`. Server authorizes each committed
operation; support specifies the content revision the user actually saw.
Root imports, site management, account deletion/recovery, moderation and billing
are not bridge commands. They open trusted standalone management pages.

Suggested limits: 64 KiB inbound message, 256 KiB response, 8 in-flight requests,
10s read/30s write timeout, bounded pages and payloads matching API limits.
Rate limits apply to both transport and backend. Large data uses pagination,
never unbounded array through postMessage. Resize messages are throttled and
clamped; child cannot navigate top or create popups without user action.

Retry safe reads with backoff; retry state assignments by idempotent semantics.
POST create/edit retains its Idempotency-Key and body digest across uncertain
transport outcomes. Timeout does not imply rollback: query/retry the same op,
never submit a new point with a different key. On logout/site navigation discard
old queued writes; do not replay under another user.

## 5. Authentication across untrusted hosts

Global accounts belong to the service, not to a Neocities site. Passwords,
recovery secrets and global bearer credentials are entered only on trusted
hosted top-level UI. Full iframe and bridge must work without third-party cookies
or unpartitioned localStorage. Do not promise silent SSO between embeds.

Proposed minimal flow for P00/P03:

- User opens trusted login/consent page through an explicit click. Popup may be
  blocked; fallback is a normal tab with a return link, not an insecure shortcut.
- Global first-party session remains at auth origin. For an embed, authorization
  uses state + PKCE, a short-lived single-use code bound to site, parent origin,
  requested capability, flow ID and child-held verifier. Arbitrary redirects
  are forbidden. A code may be relayed through the parent only if redemption
  still requires the iframe-held verifier and exact binding; no bearer leaks.
- The iframe exchanges the code with the same-origin API and keeps the resulting
  short-lived, revocable site-scoped grant only in memory. Reload requests new
  authorization. Parent receives public login status, never grant/global token.
- Expiry/revoke/account block/site disable/origin removal is checked on every
  write. Logout revokes the grant; trusted account UI can revoke all grants.
- No operator/site-admin authority is placed in an ordinary visitor embed grant.

**Consent is not optional glue.** Any page holding a bridge channel can ask it to
act. MVP writes initiated by parent are confirmed on a trusted top-level screen
showing the exact point/revision/text diff/action before commit. The service
stores an immutable bounded action intent, confirms it once and returns the
result; it does not confirm one payload and execute a later changed payload.
Full iframe also uses trusted confirmation for edits/delegation and other
sensitive changes to mitigate hostile framing/clickjacking.

For low-impact repeated reactions a later explicit grant may allow bounded
reversible writes without a confirmation for every click. Its scope and duration
must be visible: parent code can exercise it. Do not silently broaden such a
grant to posting, editing, trust, management or financial actions. UX vs per-write
confirmation is a measured P00/P03 decision, not permission to ship ambient
cross-site account authority.

Trusted service UI itself may directly perform authorized user writes under its
normal session/CSRF rules, without the third-party bridge intent ceremony.
Precise login/code TTL proposal: code60s, scoped grant15min, management session
policy separately documented. These values are initial test parameters.

## 6. Theme contract: CSS stays with site owner

External CSS does not cross into a different-origin iframe. Two supported paths:

- Local UI+bridge: owner's CSS styles the local DOM freely, bridge has no UI.
- Full iframe: saved site theme works with bare iframe; optional parent loader
  reads known computed CSS variables and sends validated theme values.

Example future integration, not a working published snippet:

```html
<iframe class="my-wiki" title="Вики этого сайта"
  src="https://embed.example/embed/v1/s_example/"
  loading="lazy" referrerpolicy="no-referrer"></iframe>
```

```css
.my-wiki {
  width: 100%; height: 75vh; border: 0;
  --node06-bg: #101018;
  --node06-text: #eeeeee;
  --node06-accent: #aaddff;
  --node06-panel: #181826;
  --node06-radius: 8px;
}
```

The CSS example styles the iframe element; an accompanying future SDK reads
these variables and transports them. Without that SDK, only width/height/border
apply from parent; internal colors use saved theme. Do not document inherited
custom properties as automatic cross-frame CSS.

`theme.set` allowlist v1 proposal: bg/text/accent/panel/border as validated color
literals, radius0–16px, font enum(system,serif,mono), density enum(normal,compact).
Unknown keys, `url`, `@import`, raw selectors/declarations, external fonts,
HTML/JS and arbitrary CSS text are rejected. Validate data and map to fixed
properties; never concatenate it into unrestricted style source. Constrain
unreadable contrast via accessible fallback and user “reset theme”.

Login/consent/security messages are fixed trusted UI, outside tenant theme.
No stylesheet URL from query string; no raw remote CSS loaded in service origin.
Advanced free-form CSS requires a separate isolated design/review. Visual theme
never alters point mass, six coordinates, confidence or rights.

## 7. SDK delivery, history and fallback

One renderer source supports local/hosted/full modes. Publish versioned SDK
assets and copyable local files for free hosts. Pin major/integrity where useful;
old pinned clients receive compatibility or readable upgrade errors, not runtime
execution of arbitrary current GitHub files. Service-owned release jobs build
our source; a user's fork never runs in our privileged environment.

The parent URL and iframe URL are different histories. Define one opt-in history
sync contract: initial parent query -> navigate intent; committed child point ->
parent replace/push at deliberate navigation; nonce/sequence avoid echo loops;
popstate replays a read navigation without duplicate push. Bare iframe maintains
its own navigation and supplies a standalone share link. Parent document title
changes only by opt-in, without exposing private/session data.

Iframe has a meaningful title, responsive height bounds, keyboard focus and
text neighbour view. Full view avoids keyboard traps and double-scroll where
possible. Reduced-motion respected independently of theme. Failed bridge shows
static roots/retry/standalone link; hidden iframe cannot silently collect drafts
or trigger writes. A plain host link remains available if iframe is blocked.

## 8. Acceptance proof

Test two controlled external origins, hosted origin and third malicious origin:
read/write with exact Neocities CSP; wrong origin/source/nonce/version; stolen
site ID; denied action; malformed payload; timeout after commit; reload and
multiple frames; origin/grant revocation; cookie/storage/popup blocked; code
replay/verifier mismatch; CSS injection; theme changes; history and deep links;
one reaction across all three clients; revision changed before confirmation.

Full embed must not accidentally receive auth-page DENY headers; auth must not
inherit permissive frame policy. Verify cache separation per site config and
that a nested hostile ancestor is refused. Public protocol never grants private
root/account data merely because public graph embedding is allowed.

Browser references (checked 13 September 2026):
[postMessage](https://developer.mozilla.org/en-US/docs/Web/API/Window/postMessage),
[same-origin policy](https://developer.mozilla.org/en-US/docs/Web/Security/Defenses/Same-origin_policy),
[frame-ancestors](https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Content-Security-Policy/frame-ancestors).
