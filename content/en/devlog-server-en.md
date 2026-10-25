Stage 4. An independent server copy

A copy of the NODE06 repository can run independently when you need your own database and administration. This is another server: accounts register there separately and influence is not transferred from neighboring servers. See [NODE06](md://node06-en) for the shared space inside one database.

The backend requires Python at least 3.12 and below 3.15, PostgreSQL and the dependencies in pyproject.toml. The setup guide covers the virtual environment, static build and service startup. A standalone static copy builds with python3 build.py; that alone does not install a database or start the social service.

Provide private configuration using backend/.env.example. The main settings are NODE06_DATABASE_URL, NODE06_MANAGEMENT_ORIGIN, NODE06_EMBED_ORIGIN and NODE06_HOSTED_DIST. The trusted wiki and embed use distinct HTTPS origins. Database passwords, cookies, backups and private configuration do not belong in the public repository or dist/.

For an update: retain a backup and a tested recovery procedure, install the selected revision, apply all its migrations with alembic upgrade head, then start behind an HTTPS reverse proxy. /api/v1/health checks the process and /api/v1/ready checks database access; readiness alone does not prove the migration head is correct. /api/v1/meta reports the build and capabilities. Separately verify login, point creation and reads from a connected site.

Automatic Git content polling does not update the engine. A fork chooses its own update policy. Rolling back an application does not imply a safe schema downgrade: permanent markers guarding deleted content cannot simply be removed after cleanup. This is a guide to the current source, not a report that your server has been deployed.

[Setup modes](https://node06.neocities.org/setup/en/)

[Backend configuration](https://github.com/wratixor/node06/blob/main/backend/README.md)

[Source snapshot: 25 October 2026](https://github.com/wratixor/node06/tree/29135cf3c31ef67cb81e4ec5fac15dfe970fc63d)

[All stages](md://devlogs-en) · [Previous stage](md://devlog-git-en) · [Русский](md://devlog-server-ru)
