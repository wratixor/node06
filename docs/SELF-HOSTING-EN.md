# NODE06: your own wiki

[Инструкция на русском](https://node06.neocities.org/setup/)

An instance shares accounts and points across its connected sites. Each site has its own entrance and theme. Register through **Account**, then use **My sites** to connect a site. Account, site management and community actions open on the trusted service; the embedding site never receives your password.

## Mode 1 — static site

Copy or fork the repository, install Python 3, run `python3 build.py`, then upload the contents of `dist/` to Neocities or another static host. Edit Markdown roots in `content/`; `md://` links must be reciprocal. Languages belong to individual points, not separate site versions. Without a connected service, only local roots are available: there are no shared accounts or database writes. Remove `static/connection.json` before building a disconnected copy so it does not link to the demo service.

## Mode 2 — your frontend with an existing instance

Register on the chosen instance, add your HTTPS site in **My sites**, place its `node06-verification.txt` file at the site root, and verify ownership. Copy its public `siteId`, `embedOrigin` and `serviceOrigin` values into `static/connection.json`, rebuild and publish `dist/`. Never put passwords or secrets in this file. The menu opens your chosen service.

Neocities Free reads shared data through a small iframe bridge instead of fetching the external API directly. Your site's CSS styles your own frontend.

[Small iframe bridge](https://github.com/wratixor/node06/blob/main/docs/PUBLIC-BRIDGE-V1.md)

## Mode 3 — embed the complete wiki

After verifying your site, paste the iframe snippet from **My sites** into your page. Its address looks like `https://YOUR-EMBED-HOST/embed/v1/YOUR-SITE-ID/`. The frame reads the shared database; sign-in and changes open on the trusted service. Use the site's theme settings for the frame: CSS on a different origin cannot style its contents. Reading needs no third-party account cookie. Never collect a service password in a form that passes it to the embedding page.

## Mode 4 — hosted wiki with Git content

If the service already exists, you do not need a second backend. The operator connects a content repository to your existing site through deployment. A manifest defines the site, Markdown roots and a homepage with configurable blocks and links. Homepage priority can favor either the repository or database settings. See `examples/root-source/`.

Validate and publish an immutable Git snapshot through deployment; do not edit the live database manually. Git roots are protected from revision voting. Accepted source updates transfer active support and publish a changelog.

[Content deployment](https://github.com/wratixor/node06/blob/main/docs/OPERATOR-CONTENT-DEPLOY.md)

[Homepage blocks and source priority](https://github.com/wratixor/node06/blob/main/docs/HOME-BLOCKS-V1.md)

## Mode 5 — independent instance

You need PostgreSQL, Python with dependencies from `pyproject.toml`, and separate HTTPS origins for the trusted wiki and embed host. A repository copy works without access to the original owner's account. Create a virtual environment; install `.[dev]` for development or a built wheel on the server.

Configure a private environment using `backend/.env.example`: `DATABASE_URL`, `MANAGEMENT_ORIGIN`, `EMBED_ORIGIN` and `HOSTED_DIST`, all prefixed with `NODE06_`. Never commit this environment or copy someone else's secrets. Configure the public frontend connection for your own instance before building; do not reuse the demo site ID or verification proof.

Build the frontend, run online `alembic upgrade head` in the service environment, and start `node06-service` behind an HTTPS reverse proxy. Registrations and influence stay local to this database. Account synchronization and cross-server subscriptions remain future work.

[Backend installation, configuration and tests](https://github.com/wratixor/node06/blob/main/backend/README.md)

[Hosted origins and isolation](https://github.com/wratixor/node06/blob/main/docs/HOSTED-WIKI-V1.md)

[Deployment and rollback](https://github.com/wratixor/node06/blob/main/docs/DEPLOYMENT-HANDOFF.md)

On the Amsterdam server, use the existing `geno-dice-deploy` scripts and local configuration. Automatic deployment tracks accepted `main` commits. After an update, check health, readiness, metadata, sign-in and reading from the real site. A successful build does not prove a successful production deployment.
