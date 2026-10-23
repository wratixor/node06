# Public iframe API bridge v1

Implemented source, not live Neocities acceptance. This is the small transport
iframe, separate from the full wiki UI. It reads the same core-root projection
and active site welcomes as the hosted wiki, including accepted Git roots. It is not a generic HTTP proxy,
authenticated embed, semantic editor or completed social API.

## Connect a verified site

1. Register/login on the trusted hosted origin, create a site in `/sites/`,
   publish its proof file and verify ownership. The active site's panel shows
   both the full iframe code and the small bridge URL.
2. Download `/bridge/assets/client.js` from the configured embed origin and
   save it on **your own static site**, for example as `/node06-client.js`.
   This allows local scripts under Neocities Free CSP; no external script
   permission, external fetch permission or service token is required.
3. Include that local script and initialize after `document.body` exists. Replace
   the example origin/ID with the deployed service and your verified site ID.

```html
<div id="meaning"></div>
<script src="/node06-client.js"></script>
<script>
(async () => {
  try {
    const bridge = await connectNode06({
      embedOrigin: 'https://embed.geno-dice.com',
      siteId: 's_REPLACE_WITH_YOUR_32_HEX_SITE_ID'
    });
    const point = await bridge.request('point.get', { point_id: 'field-ru' });
    document.querySelector('#meaning').textContent = point.preview;
    // Also supported:
    // await bridge.request('site.get');
    // await bridge.request('points.search', { query: 'воля' });
    // await bridge.request('capabilities.get');
    // bridge.close(); // removes iframe and rejects pending requests
  } catch (error) {
    document.querySelector('#meaning').textContent = 'NODE06 unavailable: ' + error.message;
  }
})();
</script>
```

The SDK creates a hidden sandboxed iframe. Your page performs no cross-origin
fetch: parent → `postMessage` → iframe → same-origin read endpoint → iframe →
`postMessage` → parent. Your own CSS styles the returned data in your own DOM;
use `textContent` for previews. Do not treat returned content as executable code.
The placeholder intentionally fails validation until replaced with a real ID.

## Actual routes and methods

- `GET /bridge/v1/{site_id}/`: transport document on the configured embed host.
- `GET /bridge/v1/{site_id}/read?method=…`: anonymous, no-store public read endpoint.
- `/bridge/assets/bridge.js`: iframe runtime; `/bridge/assets/client.js`: parent SDK.

These routes intentionally do not expose `/api/v1/auth`, management or arbitrary
API paths on the embed host. The existing proxy's `/api` deny stays in place.

| Method | Exact params | Result |
|---|---|---|
| `capabilities.get` | `{}` | Allowed methods, read-only flag, no parent credentials |
| `site.get` | `{}` | Public site ID/origin/welcome point ID |
| `point.get` | `{point_id}` | Public point from the common hosted projection |
| `points.search` | `{query}` | Legacy: up to 20 `{id, preview}` items and explicit `truncated` |
| `points.searchPage` | `{query, after?, limit?}` | Current full-body prefix matches, `{items, next_cursor}` |
| `point.read` | `{point_id}` | Current public body/HTML, revision, digest, source and bounded visible links |
| `point.neighbors` | `{point_id, after?, limit?}` | Bounded visible adjacent points, `{items, next_cursor}` |

IDs/query length: 1–128 characters. Search matches ID/preview case-insensitively,
without language filtering. Pending/inactive welcomes are excluded. This legacy
search retains its original semantics. New methods reuse the current-only API
visibility/index/pagination in [PUBLIC-POINTS-V1](PUBLIC-POINTS-V1.md). They do
not materialize the complete hosted graph. Unknown methods,
extra/duplicate params, arbitrary URL/header/credential forwarding and all writes
are rejected. Large point responses fail explicitly; no silently truncated body.
Current graph capacity guard still applies. No database migration is added.

## Channel and revocation

Wire protocol is `node06-embed/1` from EMBED-V1: random per-frame channel,
`hello`/`ready`, request ID, typed method/params, `result`/`error`. Both sides check
actual event origin and exact source window; iframe checks exact envelope/params
and a 64 KiB input cap. Up to eight reads may be pending; child timeout is 10s,
SDK timeout 11s (handshake 10s). Errors have stable codes, never private values.
The SDK closes on iframe reload and rejects pending work instead of reconnecting
silently. Create a new SDK connection explicitly after an error/reload.

Frame CSP permits only the verified site origin and trusted management origin
for operator previews. No wildcards. Every public read re-checks that the site is
active, so an already-loaded bridge stops reading after site revocation. No
cookies or browser storage are needed; child fetch uses `credentials: omit`.
Global account credentials never enter the parent or embed origin.

Writes/social actions still require scoped grants, PKCE and explicit user
consent. `point.createIntent` and similar commands return `METHOD_NOT_ALLOWED`;
there is no fallback to a user's global session. Site ownership is not visitor
consent. Do not advertise authenticated access based on public bridge success.

Validation: PostgreSQL route tests, browser fixture
`scripts/check-hosted-browser.py` (installed wheel, real HTTPS/CSP, blocked
storage/cookie boundary, SDK reads/search, rejected writes/spoofs and reload
cleanup). The browser parent is local HTTPS; actual deployed Neocities Free →
public embed acceptance remains required after the application update.


## P05b current reads and shared picker — 23 October 2026 source

The new methods are additive under the same `node06-embed/1` wire protocol;
old methods/envelopes are unchanged. Check `capabilities.get` before using them
against older servers. `points.searchPage` takes a query of 1–128 characters,
max eight terms; optional after is an ASCII point ID (or empty), optional limit
is an **integer number** 1–50 in postMessage (HTTP serializes it as decimal).
Defaults: search 20, neighbors 50. Cursor results are sorted by point ID, not
social ranking; they are not a frozen snapshot across edits. No language filter.
Private/history revisions remain inaccessible; pending/inactive/retired points
are hidden. Each call rechecks the registered site's active state and origin
boundary. Limits/error budgets/timeouts, no credentials, no arbitrary URLs and
no write methods remain intact. No new proxy exception, CORS or migration.

```javascript
const page = await bridge.request('points.searchPage', {query: 'воля', limit: 10});
const point = await bridge.request('point.read', {point_id: page.items[0].id});
const neighbors = await bridge.request('point.neighbors', {point_id: point.id, limit: 10});
// Continue with page.next_cursor / neighbors.next_cursor via after.
```

`point.read` exposes real DB revision IDs; built core still has null revision ID
and static provenance/digest. Never fabricate a revision pin. Search previews
are brief; select/read again to capture the current text, not stale search text.
A semantic selection is not support, a vote, a created edge or a saved post.

Built field/home pages now load local `assets/point-picker.js` and an identical
copy of the parent SDK as `assets/node06-client.js`. The header has a compact
search input with a magnifier submit button. Results appear in an anchored,
non-modal dropdown: debounced query, at most 10 items/page and 50 on screen,
more/empty/error states, current plain-text detail, point navigation and copyable
web address. No server HTML is inserted into the parent DOM. Clipboard rejection
leaves a selectable address. Escape or clicking outside dismisses results while
keeping the query and page; Arrow Down enters the results.
slow responses cannot overwrite a newer query. Raw Markdown in the detail preview
is intentional; Open leads to the existing rendered point view.

Transport selection:

- Hosted wiki: same-origin anonymous current-point API.
- Full embed: its same-origin registered public bridge read endpoint; embed /api
  remains blocked, so no parent credentials are borrowed.
- Static NODE06/Neocities: locally copied SDK -> hidden iframe -> typed read.
  `static/connection.json` configures exact HTTPS embedOrigin/serviceOrigin and
  the existing verified siteId. The committed NODE06 config uses its existing
  Neocities entry. Forks/other sites must change these public values to their
  own registration/instance; the site ID is not a credential. Invalid/unavailable
  configuration gives an explicit error, never a silent local-only result set.

Static search shows shared results in the dropdown; Open points to the hosted
entrance in a new tab, preserving a locally maintained static field. Hosted/full
Open retains the current entrance path. This slice does not replace the static
map with a live graph or provide an authenticated post editor.

A future editor can call `openNode06Picker({onSelect(point) { ... }})` on a built
field page. Its Select button returns only id, lang, current revision_id (nullable),
content_digest, preview and href. It re-reads detail on each selection; nothing
is persisted, supported or posted automatically. The normal header search does
not display a Select button or imply that authoring already exists.

Rollout: merge/review engine main; existing Amsterdam autodeploy rebuilds installed
assets. Neocities publication remains its separate GitHub main build. During an
older-server/new-static overlap, missing capabilities show Server update required;
retry after server deployment. This source change does not assert production or
real-Neocities acceptance. Validate actual iframe/CSP behavior after publication.

P05b validation: full disposable PostgreSQL suite 190 passed; targeted 27 route
checks passed. Installed-wheel HTTPS Chromium fixture passed hosted/full/static
picker flows, current selection metadata, safe raw-text display, cursor paging,
empty/error recovery, stale query suppression, Escape, rejected new malformed
params, legacy SDK reads, spoof/reload handling and cookie/storage isolation.
The static parent uses connect-src self with an allowed external frame. Current
Chromium needs an explicit local-network-access permission **only for the disposable
localhost fixture origin** to reach its loopback embed server; no production flag,
policy or browser setting is changed. Direct parent cross-origin fetch still fails
under CSP. Mobile (390px) and desktop (1440px) screenshots were inspected locally.
Real deployed Neocities is still a separate post-publication check.


Header search refinement, 23 October 2026: replaces the separate search-launch
button/modal with an always-visible rounded input and SVG magnifier in the
existing entrance palette. Enter/icon submit, typing debounces, and Escape/outside
click close only the results. The shared editor onSelect contract is retained.
The dropdown follows the input on scroll/resize and fits desktop/mobile viewports.
No API/bridge/auth/DB changes. Built CSS/browser scripts use content-hash query
versions; the first-party editor uses matching hashes from the actual hosted
bundle, preventing stale cached CSS from leaving new controls unstyled.
