# Repository devlogs

Owner request, 22 October 2026: after the engine work, prepare several short
stage posts through Markdown repositories. NODE06 content is now authored in
source (25 October); Godot-client posts remain the next content packet.
Source readiness does not confirm publication.
Each post is a normal point with explicit links to relevant concepts and adjacent
stages. RU and EN, when both are authored, are independent linked points; never
locale-specific frontends. Choose public navigation via each entrance's manifest
home blocks; imported content does not create votes or new influence.

## NODE06: engine setup and server deployment

Destination: NODE06's public root content for its existing Neocities entrance.
First inspect the actual manifest/binding and accepted source before adding files;
do not assume an arbitrary Markdown file is automatically published.

Authored NODE06 sequence:

1. Shared meaning-space: points, connections, independent languages, site versus
   user, different entrances and repository home blocks.
2. Neocities Free: iframe bridge/full embed, hosted copy, styles and current read
   boundaries, with a tested copy-and-paste example using the registered site.
3. Configure repository roots: manifest, stable IDs, links, cards and Git/UI source
   priority, immutable validation and operator content publication.
4. Deploy an independent instance from a repository copy: supported Python/PG,
   HTTPS/wiki/embed origins, private config, online migrations, readiness,
   backups, controlled updates and rollback. Only sanitized example values.

Use maintained setup/deployment contracts as sources. Distinguish implemented authoring/votes/source imports from remaining
cross-server synchronization and scoped embed authorization. Do not publish host access,
credentials, verification keys, private logs or internal topology.

## Geno-Dice Wiki: completed Godot client development

Destination: the existing `wratixor/geno-dice-wiki` content-only repository and its
registered wiki entrance, with publication through the ordinary deploy binding.
No second backend, registration or code fork is needed.

Before writing, audit current `geno-dice-arena-client` code/history and matching
project records. Extract a few completed stages (candidate themes: application
shell/account, dice and inventory, battle presentation, persistent UI/settings).
These themes are a writing outline, **not confirmation that each is finished**.
Confirm the actual chronology and public scope rather than inventing dates,
features or claiming local work shipped in a release.

Each stage post needs:

- A concrete player-facing problem and the implemented result.
- Verified source commit/date and a concise validation reference; distinguish
  source, tested build and deployed/exported version.
- Two or three useful implementation details and known remaining work.
- Links to game/client/skill concepts and previous/next posts, plus only verified
  public images if useful. No hidden lore or private production data.

Acceptance: manifest/preflight checks on committed immutable content; all local
point links resolve; home links show topic/stage rather than language partitions;
reviewed content merged before explicit operator publication; verify accepted
source SHA and actual public pages after deploy. Author the posts only after the
engine milestone, as requested, and keep source evidence with the draft.


## NODE06 source packet — 25 October 2026

Implemented four independent RU/EN stage pairs plus two language-specific index
points: `devlog-space-*`, `devlog-embed-*`, `devlog-git-*`, `devlog-server-*` and
`devlogs-*`. Each stage links to its index, adjacent stage, counterpart and an
existing concept with reciprocal links. The home has a development-log card in
each language, targeting its independent index. Old point IDs and old coordinate
entries are retained. New points use a neutral `[4,4,4,4,4,4]` root seed in both
languages; this is a provisional display baseline, not influence or lore.

This repository's `content/` tree is the actual static/core source read by
`build.py`, not a `node06-roots.json` tenant import. `static/connection.json`
selects the existing Neocities entrance `s_9b7bc95affa440f08ae8265c299cc2c6`;
its public welcome remains UI-managed. Content publication therefore needs the
usual Neocities static build/publication and server engine build/deployment for
hosted core projection. No new content-source registration is introduced.

Evidence baseline: NODE06 main `29135cf3c31ef67cb81e4ec5fac15dfe970fc63d`,
verified source contracts SELF-HOSTING, PUBLIC-BRIDGE, GIT-SOURCES, HOME-BLOCKS,
HOSTED-WIKI and actual migration head `0019_git_sources`. These are thematic
stages of the current engine, not invented dates for individual feature releases.
Public prose links to the pinned source snapshot and maintained setup guides.
No host access details, passwords, proof values or private topology are copied.
The deployment handoff no longer incorrectly names migration0004 as current;
operators must compare `alembic heads` and `alembic current` for their revision.

The separate Geno-Dice Wiki home was independently read through its public API
on this date: engine29135cf, effective Git home with default ru and translation en.
This verifies the earlier home packet, not deployment of these new devlogs.
Godot posts require a separate audit of that client's current code/history,
as specified above. No Godot achievements are inferred from this engine packet.
