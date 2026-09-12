# NODE06

NODE06 is an experimental static knowledge field and the planned root layer of a social knowledge graph.

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

The later backend is intentionally separate from the static repository and from `geno-dice.com`. Planned capabilities include user points, creation of new points attached to existing points, support/opposition, delegated trust, chronological feeds, and derived social geometry. Root Markdown points remain repository-backed.

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

The site root is a bilingual welcome page. Russian and English links lead to separate Russian and English root points; they are independent points rather than locale variants of one object.
## Field projection

The root-era map keeps the Hexrelatum six-component contract: three opposed pairs are folded into a local 3D projection only for navigation. The six axis ends use the same complementary preview pairs as Hexrelatum: cyan/red, magenta/green, yellow/blue. A visible unit sphere separates direct links (inside) from depth-2 context (outside). Root-era coordinates are deterministic synthetic values generated at build time; the future social backend will replace them with derived coordinates.

