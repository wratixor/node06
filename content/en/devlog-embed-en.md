Stage 2. Your page, a shared wiki

A static host does not need to run a backend. You can embed the complete wiki in an iframe, or keep a local map and read the shared database through a small bridge iframe. These are different entrances, not different databases. See [links](md://links-en) for graph connections.

Register on the chosen server, add your HTTPS site in My sites, publish the supplied node06-verification.txt and verify ownership. Then copy the iframe for your own registration. NODE06 already has a [public entrance](https://embed.geno-dice.com/embed/v1/s_9b7bc95affa440f08ae8265c299cc2c6/). It belongs to the existing Neocities site; another origin needs its own registration.

Example markup for the existing NODE06 entrance:

<iframe src="https://embed.geno-dice.com/embed/v1/s_9b7bc95affa440f08ae8265c299cc2c6/" title="NODE06" width="100%" height="700" loading="lazy"></iframe>

For a local map, set siteId, embedOrigin and serviceOrigin in your copy's static/connection.json. These values are public. Build the frontend and publish dist/. The bridge reads public data on its own origin, so the Neocities page needs no direct database request. A full iframe uses the wiki's theme settings: parent CSS cannot cross an origin boundary.

Enter passwords only on the trusted server. On a connected static copy, the editor can open over the map, but publication requires confirmation in a trusted window. The public bridge receives no global session and does not become a write API.

[Connection instructions](https://node06.neocities.org/setup/en/)

[Source snapshot: 25 October 2026](https://github.com/wratixor/node06/tree/29135cf3c31ef67cb81e4ec5fac15dfe970fc63d)

[All stages](md://devlogs-en) · [Previous stage](md://devlog-space-en) · [Next stage](md://devlog-git-en) · [Русский](md://devlog-embed-ru)
