# Hosted wiki and read-only iframe — first server test packet

Настраиваемая главная с тематическими блоками: [HOME-BLOCKS-V1](HOME-BLOCKS-V1.md).

Owner direction, 22 October 2026: host the game/open-lore frontend at
`wiki.geno-dice.com` and the common NODE06 backend on the Amsterdam server.
These are one service, graph and account system; the Neocities demo keeps its
static roots and will embed the same service. This is not a second database,
localized site version or isolated canon namespace.

Implemented routes (with `NODE06_HOSTED_DIST` configured):

| Route | Purpose |
|---|---|
| `/` | Game/lore entrance; optional configured site's welcome point |
| `/sites/{s_id}/` | An active site's default welcome in the shared graph |
| `/data/points.json` | Read projection of built core roots + directory + active sites |
| `/embed/v1/{s_id}/` on embed origin | Read-only full iframe with exact parent policy |
| `/assets/*`, favicon/manifest | The same built frontend and supplied icons |
| `/sites/` | First-party owner management UI |
| `/account/` | First-party account UI, linked to site management |

`/sites/` provides create/list/pagination, one-time proof display/download,
renewal/verification, welcome/name/theme editing. Network and session failures
retain form values. A 409 shows current server text/settings beside the retained
draft, with explicit choices to load the server version or save the reviewed
draft against the new revisions. A successful create displays its proof even if
the follow-up private GET fails. Git-owned/inactive welcome editing is disabled.
Proof is retained only in page memory, not localStorage or an extra server copy.

## Public projection and rendering

The immutable build's `dist/data/points.json` remains the authority for the 51
Git roots in this packet. PostgreSQL provides public active sites and the
temporary `all-sites` directory. Each active site is linked to that directory;
pending/inactive site text, challenges, ownership and sessions are omitted.
This combines two public projections for the renderer; it is not the P04 root
importer, and does not claim that all static roots have already been imported
into PostgreSQL. Generic point editing/imports and semantic links remain future.

Static root coordinates are unchanged. Site/directory coordinates are null and
labelled `display-only`; the renderer uses its display fallback rather than
inventing social coordinates or weight. Site welcome is escaped plain text,
including raw HTML; only reviewed built root HTML is rendered as HTML. Root
and site point provenance is shown in the reader. The graph includes all text
languages and allows unpaired/mixed-language welcomes.

This initial in-memory projection has an explicit safety cap, default 200 active
sites (`NODE06_HOSTED_SITE_LIMIT`, range 1–1000). Exceeding it returns 503
`GRAPH_CAPACITY_EXCEEDED`, never a silently incomplete graph. Paged neighborhood
queries/directory are required before expansion beyond the preview budget.
Other DB availability failures produce 503. The client displays a retry message;
it does not mistake missing server data for a successful empty graph.

## Two origins, one backend

Production configuration proposal:

```text
NODE06_MANAGEMENT_ORIGIN=https://wiki.geno-dice.com
NODE06_EMBED_ORIGIN=https://embed.geno-dice.com
NODE06_HOSTED_DIST=/opt/node06/app/dist
NODE06_HOSTED_TITLE=Geno-Dice Wiki
# Set after the site's owner verifies wiki.geno-dice.com:
# NODE06_DEFAULT_SITE_ID=s_<32 lowercase hex digits>
```

Both origins require HTTPS with no path/trailing slash. They must have different
hostnames, not merely different ports, because cookies are not port-isolated.
Configured embed deployments fail startup on invalid origin separation.
The host-only `__Host-node06-session` stays on the management hostname.
The app denies account, site management and private API paths on other origins;
the reference embed Nginx block also denies all `/api`, `/account`, `/sites`.

An iframe is served only on the configured embed origin and for an active site.
Its `frame-ancestors` names that site's verified exact origin plus the trusted
management origin for preview. No wildcard Neocities permissions are used.
Login/management and standalone wiki deny framing. Both hostnames proxy to the
same backend/DB; public frame reads use `/data/points.json` on their own origin.
This packet gives the parent no credentials and includes no authenticated writes,
postMessage bridge, PKCE or scoped embed grant. Those remain the next auth slice.

The iframe starts at the site's welcome. An explicit public `p` overrides the
centre. Moving to other points stays in the same site shell/theme; Home returns
to its site point, All sites to the shared directory. Saved theme tokens apply
only to that public renderer; account and management UI use their own stylesheet.
Storage denial inside an iframe falls back to default view preferences; no
third-party cookie or localStorage is required for reading.

## Build and local validation

```bash
python3 build.py
.venv/bin/python -m pip wheel --no-deps --wheel-dir /tmp/node06-wheel .
```

The wheel includes the management HTML/JS through setuptools package data; the
generated frontend `dist` is shipped beside the installed app from the same
Git revision. Use `pip wheel`, not `python -m build` from the repository root:
the existing project `build.py` shadows that module name.

Backend checks use the existing disposable PostgreSQL fixture. Browser scripts:
`scripts/check-static-navigation.cjs` checks the static demo;
`scripts/check-hosted-wiki.cjs` expects two local HTTPS servers, a disposable DB,
an active fixture owned by `fixture-owner` with synthetic password
`fixture-test-password`, verified parent `https://garden.localhost`, saved theme
`bg: #123`, and environment `NODE06_TEST_ACTIVE_SITE`. It intentionally refuses
non-local server origins. It tests real forms/cookies, proof download/renewal,
conflict/session draft retention, a failed post-create GET, the shared graph and
read-only iframe under same-origin-connect CSP with blocked storage. The trusted
management page supplies an explicit iframe preview; actual embed requests are
checked for absence of the global cookie (not just the automation cookie jar).

A synthetic public parent → localhost frame was correctly blocked by Chromium's
local-network-access checks. The acceptance test therefore uses a real local HTTPS preview page;
this does not prove real Neocities acceptance. After deployment, explicitly test
Neocities Free → the actual public Amsterdam embed origin in target browsers.

Run the reproducible fixture (it builds/installs the wheel, creates a random
schema in the disposable test DB, starts two local TLS servers and cleans up):

```bash
NODE06_TEST_DATABASE_URL='postgresql+psycopg://.../node06_test_preview' \
  .venv/bin/python scripts/check-hosted-browser.py
```

Supply Playwright through `NODE_PATH` if using a bundled runtime, and
`NODE06_BROWSER_EXECUTABLE` if Chrome is not at `/usr/bin/google-chrome`.
This fixture intentionally bypasses certificate validation only for its generated
loopback certificate; production proof verification always validates public TLS.

First deployment procedure and remaining operator checks:
[AMSTERDAM-FIRST-DEPLOY.md](AMSTERDAM-FIRST-DEPLOY.md).

Verified source: `ac14f27`, branch `f-20261022083906-hosted-wiki`, target `main`.
[Remote CI](https://github.com/wratixor/node06/actions/runs/39737812411) passed
with 93 PostgreSQL-backed tests, Ruff, static/protocol checks and wheel packaging.
The installed-wheel local HTTPS browser fixture also passed; live Amsterdam and
Neocities acceptance remain pending.
