# NODE06

NODE06 is an experimental static knowledge field and the first public surface of a rethought concept engine.

The static frontend works without a backend: root points are Markdown files, reciprocal `md://` links form the graph, `build.py` validates and renders the field, and the generated `dist/` directory is deployed to Neocities.

NODE06 is based on [Hexrelatum](https://github.com/wratixor/hexrelatum). See [LICENSES.md](LICENSES.md) and [NOTICE.md](NOTICE.md).

Self-hosting and connection modes: [English installation guide](docs/SELF-HOSTING-EN.md), published at `/setup/en/`. [Русская инструкция](docs/SELF-HOSTING.md) — `/setup/`.
Accounts, site management and community links in static copies use `serviceOrigin`
from `static/connection.json`; hosted copies use their configured management origin.

Development log: [English index](content/en/devlogs-en.md), [Русский указатель](content/ru/devlogs-ru.md).
Four stage posts cover the shared graph, embedding, Git roots and independent servers.
These are ordinary linked points; the home page selects the matching index.

## Repository structure

```text
content/              root Markdown points
static/               browser CSS/JS
static/icons/         owner-supplied favicon and app icons/manifest
build.py               validator + static builder
scripts/build.sh       local build shortcut
scripts/publish.sh     build + commit + push shortcut
.github/workflows/     CI / Neocities deployment
docs/                  setup notes
dist/                  generated output (ignored by Git)
```

## Root point format

The file name is the point ID. IDs use lowercase ASCII letters, digits and `-`.

Internal point links use:

```markdown
[some text](md://other-point-id)
```

Every internal relation must appear in both Markdown files. The build fails when an internal target is missing or a relation is not reciprocal.

Normal `http://` and `https://` Markdown links remain external links.

## Build

```bash
./scripts/build.sh
```

or:

```bash
python3 build.py
```

The builder publishes `static/icons/` at the site root and includes favicon,
Apple touch icon and manifest links in every generated HTML page. Keep the
manifest icon paths rooted at `/`; the same files serve all point languages.

## Publish changes

After the GitHub remote and Neocities secret are configured:

```bash
./scripts/publish.sh "describe the change"
```

The script builds locally, stages source changes, commits, and pushes. GitHub Actions rebuilds from source and deploys `dist/` to Neocities.

For the first GitHub push from the current repository state, read [docs/FIRST-PUSH.md](docs/FIRST-PUSH.md).

## Shared service and social layer

The baseline backend/API design is recorded in [docs/API-V1.md](docs/API-V1.md).
The detailed implementation sequence, open decisions and agent handoff are in
[docs/IMPLEMENTATION-PLAN.md](docs/IMPLEMENTATION-PLAN.md) (Russian).

The service uses one shared database, graph and user identity across
independent sites. Each site has its own welcome point and can import additional
Markdown roots from a registered GitHub fork. Public lore joins the same graph.
Authors edit unsubscribed points directly; subscribed text changes through
revision proposals and explicit influence-weighted votes. Durable notifications
prevent a supported meaning from changing unnoticed. Optional word links
let authors choose precise definitions through search.

Amsterdam is intended to serve the backend and the common hosted frontend.
Neocities Free integration uses a small iframe bridge for a local interface or
a full embedded wiki. See [embedding contract](docs/EMBED-V1.md) and
[Git root import contract](docs/ROOT-IMPORT-V1.md). Direct external API requests
are blocked by the current Neocities CSP; external frames are allowed, but the
implemented transport is tested with local HTTPS origins; real-origin acceptance
remains a separate deployment check.
P01/P02, first-party accounts/site management UI, hosted public graph and a
read-only full iframe are implemented locally. Scoped embed auth remains future work; deployment state must be verified separately. See [hosted wiki setup](docs/HOSTED-WIKI-V1.md).
Current setup and validation are in [backend/README.md](backend/README.md), with
implemented payloads in [AUTH-V1](docs/AUTH-V1.md) and
[SITE-MANAGEMENT-V1](docs/SITE-MANAGEMENT-V1.md). The static root field remains
the Neocities frontend.

A local two-origin transport prototype is available in
[`prototypes/embed-p00/`](prototypes/embed-p00/). It is a CSP and iframe protocol
check with synthetic data, not a backend or deployable embed SDK.

Implemented subscriptions, trust and influence-weighted revision ballots:
[SOCIAL-V1](docs/SOCIAL-V1.md). This source packet is separate from deployment;
read-only embedding does not grant authenticated write access.

## Navigation model

The field is the primary interface. Point text is secondary and opens as an overlay above the field; opening a point does not navigate away from the graph. Stable `/p/<id>/` URLs remain only as compatibility/deep-link entry points and redirect into the field overlay.

## v0.3 field interaction

The field is the primary interface. Selecting a sphere always makes it the new center.

- **READ** (default): recenter and open the selected point text.
- **EXPLORE**: recenter only, without automatically opening text.
- **FEED**: personal creation-only stream on the trusted server, with older occupied UTC days loaded explicitly. Static/iframe copies link to that private feed. See [contract](docs/CREATION-FEED-V1.md).
- Text can be docked **RIGHT** (default), **BELOW**, or **OVERLAY**.
- Drag the field or use arrow keys / WASD to rotate it; mouse wheel or Q/E changes zoom.
- Six coloured axis rays are orientation aids in the static era. Their labels are intentionally absent from the public field. The root-era seed is stored in `content/root-coordinates-v1.json`; future social coordinates remain separately derived and attributable.

The site root is a bilingual welcome page. The NODE06 header link and field
heading lead to `/`. All point URLs use `/?p=<id>&open=<id>`; the field, feed and
recent activity are shared. Language describes a point's text only. There are no
RU/EN application versions, locale routes, translation identities or language
filters. Any point can be in any language; authored Russian and English points
are separate objects connected by ordinary links. Old `/ru/` and `/en/` URLs
only redirect to the common entrance, preserving an explicit point query.
Coincident seed coordinates never merge identities: display-only separation
keeps both spheres present without changing their stored coordinates.

Browser regression checks: build, serve `dist`, then run
`NODE06_PREVIEW_URL=http://127.0.0.1:8766 node scripts/check-static-navigation.cjs`
in an environment providing Playwright. Set `NODE06_BROWSER_EXECUTABLE` to use
an installed Chromium/Chrome. The check covers every root's depth-2 neighborhood,
mixed-language navigation, legacy redirects, shared feeds and the welcome page.
## Field projection

The root-era map keeps the Hexrelatum six-component contract: three opposed pairs are folded into a local 3D projection only for navigation. The six axis ends use the same complementary preview pairs as Hexrelatum: cyan/red, magenta/green, yellow/blue. A visible unit sphere separates direct links (inside) from depth-2 context (outside). Root-era coordinates come from a versioned, validated seed model rather than from ID hashes. The future social backend adds separately-derived social coordinates; it must not present the seed as community judgment.

The internal root-coordinate contract is documented in
[docs/ROOT-COORDINATES-V1.md](docs/ROOT-COORDINATES-V1.md). It deliberately
keeps semantic axis labels out of the public field.

Small public iframe API bridge for Neocities/local UI: [connection guide](docs/PUBLIC-BRIDGE-V1.md).
Copy the SDK onto your own site; anonymous shared reads only, no authenticated writes yet.
