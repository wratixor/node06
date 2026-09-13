# NODE06

NODE06 is an experimental static knowledge field and the first public surface of a rethought concept engine.

The first version is intentionally backend-free: root points are Markdown files, reciprocal `md://` links form the graph, `build.py` validates and renders the field, and the generated `dist/` directory is deployed to Neocities.

NODE06 is based on [Hexrelatum](https://github.com/wratixor/hexrelatum). See [LICENSES.md](LICENSES.md) and [NOTICE.md](NOTICE.md).

## Repository structure

```text
content/              root Markdown points
static/               browser CSS/JS
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

## Publish changes

After the GitHub remote and Neocities secret are configured:

```bash
./scripts/publish.sh "describe the change"
```

The script builds locally, stages source changes, commits, and pushes. GitHub Actions rebuilds from source and deploys `dist/` to Neocities.

For the first GitHub push from the current repository state, read [docs/FIRST-PUSH.md](docs/FIRST-PUSH.md).

## Planned social layer

The baseline backend/API design is recorded in [docs/API-V1.md](docs/API-V1.md).
The detailed implementation sequence, open decisions and agent handoff are in
[docs/IMPLEMENTATION-PLAN.md](docs/IMPLEMENTATION-PLAN.md) (Russian).

The planned service uses one shared database, graph and user identity across
independent sites. Each site has its own welcome point and can import additional
Markdown roots from a registered GitHub fork. Public lore joins the same graph.
Authors can edit their points; revision-aware support and change notifications
are proposed to prevent silent changes to endorsed meaning. Optional word links
let authors choose precise definitions through search.

Amsterdam is intended to serve the backend and the common hosted frontend.
Neocities Free integration uses a small iframe bridge for a local interface or
a full embedded wiki. See [embedding contract](docs/EMBED-V1.md) and
[Git root import contract](docs/ROOT-IMPORT-V1.md). Direct external API requests
are blocked by the current Neocities CSP; external frames are allowed, but the
chosen transport still needs a browser prototype and real-origin validation.
None of this service has been implemented or deployed. The static builder and
existing root format described above remain the implemented baseline.

A local two-origin transport prototype is available in
[`prototypes/embed-p00/`](prototypes/embed-p00/). It is a CSP and iframe protocol
check with synthetic data, not a backend or deployable embed SDK.

## Navigation model

The field is the primary interface. Point text is secondary and opens as an overlay above the field; opening a point does not navigate away from the graph. Stable `/p/<id>/` URLs remain only as compatibility/deep-link entry points and redirect into the field overlay.

## v0.3 field interaction

The field is the primary interface. Selecting a sphere always makes it the new center.

- **READ** (default): recenter and open the selected point text.
- **EXPLORE**: recenter only, without automatically opening text.
- **FEED**: keep the map visible and show points ordered by latest interaction.
- Text can be docked **RIGHT** (default), **BELOW**, or **OVERLAY**.
- Drag the field or use arrow keys / WASD to rotate it; mouse wheel or Q/E changes zoom.
- Six colored axis rays are orientation aids in the static era. They do not represent social coordinates yet.

The site root is a bilingual welcome page. The NODE06 header link and field
heading lead to `/`. Russian and English links lead to separate Russian and
English root points; they are independent points rather than locale variants
of one object. The implementation plan tracks remaining language-filter and
cross-language navigation inconsistencies.
## Field projection

The root-era map keeps the Hexrelatum six-component contract: three opposed pairs are folded into a local 3D projection only for navigation. The six axis ends use the same complementary preview pairs as Hexrelatum: cyan/red, magenta/green, yellow/blue. A visible unit sphere separates direct links (inside) from depth-2 context (outside). Root-era coordinates are deterministic synthetic values generated at build time; the future social backend will replace them with derived coordinates.
