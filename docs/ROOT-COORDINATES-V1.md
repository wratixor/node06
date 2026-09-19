# Root coordinates v1

`content/root-coordinates-v1.json` is the Git-owned initial layout for NODE06's
static root era. It replaces the former ID-hash layout with a reviewable seed,
while keeping the public field free of semantic axis labels.

## Contract

- Six hidden system **Ancients-anchors** are named after `body`, `spirit`,
  `onslaught`, `composure`, `reaction`, `technique`. They are internal service
  fixtures: no login, public profile, graph sphere or ordinary user weight.
- Each root stores six `anchor_weights`, one contribution from each Ancient.
  The emitted coordinate is `1 + anchor_weight` per component, so the ordinary
  root range remains `1..9` while the provenance of every initial direction is
  explicit and testable.
- The renderer folds each opposed pair into its existing local 3D navigation
  projection. The public rays stay unlabelled; this file is not copied into
  `dist/`.
- The component order preserves the visible complementary colour directions:
  cyan/red, magenta/green and yellow/blue. It does not claim that a social
  concept literally is a combat stat.
- Every root point must be represented exactly once. Anchor weights are finite
  values in `0..8`, so emitted ordinary-root coordinates stay in `1..9` and
  never occupy a pure pole.
- Each listed Russian/English pair is an independent point pair with starting
  component distance at most `0.5`. In v1 their coordinates are equal on
  purpose: language does not create a social difference before a social layer
  exists.
- `build.py` validates all of the above and emits the model version as
  `coordinate_source` in `dist/data/points.json`.

## Meaning of the seed

The seed uses the approved game-stat polarity as an internal mnemonic:

| Yang-facing | Yin-facing |
| --- | --- |
| Body | Spirit |
| Onslaught | Composure |
| Reaction | Technique |

This is a symbolic reading of action and holding, not a gender classifier and
not a moral ranking. The public `polarity-*` roots make that boundary explicit.
The familiar black/white taijitu is a design reference for interdependence: a
polarity contains a trace of its opposite and can change by relation. It is not
an instruction to render every point as black or white.

The six anchors model only the **root-era test seed**. They do not receive
community support, do not contribute reputation, and cannot stand in for real
participants. Their weight is fixed at `1`; changing a root's six anchor
weights is a reviewed content/model change, not a social vote.

The future social coordinate is a separate, derived projection from explicit
community behaviour. It may differ from this seed and must record its own
space/version/provenance rather than overwriting it. That visible difference is
part of the intended experiment, not an inconsistency to hide.
