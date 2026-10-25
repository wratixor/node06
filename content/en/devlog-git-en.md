Stage 3. Repository roots and home pages

Roots describe the foundation of a particular wiki. NODE06 can keep them in Git, separately from user posts. This starting foundation relates to the [root era](md://root-era-en); the running service adds user points and reactions to it.

A content repository provides node06-roots.json and the Markdown files it lists under site-content/. Keeping a local ID preserves a point's identity; md://local/<id> links resolve to entrance-scoped IDs. The engine reads an immutable commit and validates files and links. It does not execute the content fork's code, workflows or dependencies.

An owner connects a source through My sites → GitHub roots: choose a public repository and branch, add the issued ownership proof, then preview and explicitly accept publication. Use the proof issued for your source, not an invented or copied example. After the first publication, choose manual updates or checks every 15 minutes. Sources already bound by an operator continue through their existing deployment path.

The home_page field defines home blocks. default_language and translations hold complete variants with their own destinations: a Russian World button can lead to one point, and an English button to another. Git, site-settings or welcome priority selects the whole home document. Point IDs do not require language suffixes.

Changing only the home layout does not create a semantic point revision. An accepted Git text update changes a protected root through its source, automatically transfers its active support and appears in the changelog.

[Content repository example](https://github.com/wratixor/node06/tree/main/examples/root-source)

[Connecting Git](https://github.com/wratixor/node06/blob/main/docs/GIT-SOURCES-V1.md)

[Source snapshot: 25 October 2026](https://github.com/wratixor/node06/tree/29135cf3c31ef67cb81e4ec5fac15dfe970fc63d)

[All stages](md://devlogs-en) · [Previous stage](md://devlog-embed-en) · [Next stage](md://devlog-server-en) · [Русский](md://devlog-git-ru)
