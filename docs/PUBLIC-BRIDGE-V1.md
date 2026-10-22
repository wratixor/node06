# Public iframe API bridge v1

Implemented source, not live Neocities acceptance. This is the small transport
iframe, separate from the full wiki UI. It reads the same core-root projection
and active site welcomes as the hosted wiki. It is not a generic HTTP proxy,
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
| `points.search` | `{query}` | Up to 20 `{id, preview}` items and explicit `truncated` |

IDs/query length: 1–128 characters. Search matches ID/preview case-insensitively,
without language filtering. Pending/inactive welcomes are excluded. This initial
search is not the later indexed semantic search/editor. Unknown methods,
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
