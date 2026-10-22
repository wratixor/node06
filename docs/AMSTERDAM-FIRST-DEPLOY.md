# First Amsterdam deployment — preparation, not completed deployment

Target chosen by the owner: one common backend on Amsterdam, game/open-lore
entrance at `wiki.geno-dice.com`, separate read-only frame at
`embed.geno-dice.com`. The latter is the implementation's proposed technical
hostname; no DNS/certificate/server change has been made in this packet.

The application is ready for local/CI preview validation. Actual host inventory,
installation of the prepared deploy target and actual Nginx/certificate checks remain
operator work before production. Do not treat the example files as installed.
Backend architecture/limitations: [HOSTED-WIKI-V1](HOSTED-WIKI-V1.md).
Account/site contracts: [AUTH-V1](AUTH-V1.md), [SITE-MANAGEMENT-V1](SITE-MANAGEMENT-V1.md).

## Existing operator path

A reviewed-source integration is prepared in the private deployment repository:
[NODE06 operator runbook](https://git.geno-dice.com/Wratixor/geno-dice-deploy/src/branch/f-20261022091458-node06-deploy/docs/NODE06_DEPLOYMENT.md),
branch `f-20261022091458-node06-deploy`, target `develop`, later reviewed promotion
to `main`. It adds explicit Amsterdam `--project node06`, never a host-wide timer.
Its check-only, environment validation, backup/migration/health ordering and
permission boundaries have local fixtures. Source publication does not install it.

The authoritative unit/proxy/env/config examples live in that repository:
`systemd/node06.service.example`, `nginx/node06.conf.example`,
`nginx/node06-proxy.conf.example`, `config/node06.conf.example`,
`env/node06.env.example`. The application repository does not maintain a second
copy or a second automatic SSH deployment path.

Paths/names are proposed layout, not observed Amsterdam state. MemoryMax 512 MiB,
16 HTTP concurrency slots and 64 tasks are initial protective limits, not measured
host capacity. Inspect live CPU/RAM/process/DB usage and adjust before opening
registration. Keep the shared proof/auth budgets consistent across workers.
No Wallet, Arena balance, payment service or Moscow secret is needed here.

## Operator deployment order

1. Verify Amsterdam host identity, current deployment toolkit, DNS control,
   available port/resources, supported Python and PostgreSQL, existing vhosts and
   certificate issuance/renewal method. Record a sanitized inventory in the
   deployment project. Do not run a new sudo/install command based on guessed paths.
2. Review/merge this application branch and promote the separate operator integration through develop/main.
   Deploy an exact application commit; retain a previous release where one exists.
3. Create dedicated unprivileged runtime identity and UTF-8 NODE06 DB/role. No shared
   game/Wallet DB or copied financial credentials. Supply the DSN through the
   root-managed env file. Add the two DNS records to the verified Amsterdam address
   and provision certificates using the existing operator method before enabling
   these TLS vhosts. Do not weaken TLS validation to make claims pass.
4. Build the root frontend and wheel from that same revision, install the wheel
   and dependencies in the runtime venv, and set `NODE06_HOSTED_DIST` to that
   release's generated `dist`. Configure both HTTPS origins as in HOSTED-WIKI-V1.
5. Apply `alembic upgrade head` with the new environment (head
   `0004_verifier_leases`). Preserve full migration diagnostics. This packet adds
   no migration beyond the previous site API revision. A fresh DB is expected;
   if an earlier NODE06 DB exists, take/rehearse a protected backup first.
6. Start the dedicated service through the reviewed operator pipeline. Check
   loopback `/api/v1/health`, `/api/v1/ready` and `/api/v1/meta`; readiness currently
   checks connectivity, so verify Alembic revision separately. Validate Nginx
   with actual installed paths/certificates before reload, then test both public
   TLS names. Do not replace unrelated vhosts or restart the entire host.
7. Open `/account/`, register the owner, save the emergency code privately and
   log in. In `/sites/`, claim `https://wiki.geno-dice.com`, write its welcome and
   download the proof. Publish that exact file using the operator-owned persistent
   proof location; the application must never auto-publish a challenge for a
   caller, which would let anyone prove ownership of the service hostname.
8. Verify the site through the UI. Set its `s_` ID as `NODE06_DEFAULT_SITE_ID` and
   apply that configuration through the operator pipeline. `/` now opens the
   wiki's welcome point. Register the Neocities demo separately; publish its proof
   via Neocities and use its own iframe code/point in the same graph.

## Acceptance before opening use

Check the actual deployed build revision, root/static assets/favicons, account
registration/login/recovery, retained error inputs, and pending/active owner flows.
Confirm editing a stale welcome gives 409 and does not lose the draft. Public
graph must include both RU/EN roots and active sites, never pending proof/private
data. Confirm HTML-looking welcome text displays as text.

Check the exact `frame-ancestors` header for each registered site, a real
Neocities Free parent, and rejection of an unrelated parent. A frame must retain
its home/theme while navigating, read without third-party storage, and be unable
to use global account/session/management APIs on the embed hostname. Parent CSS
does not reach the frame; saved theme tokens do. This remains a read-only iframe,
not the authenticated bridge/social layer.

## Recovery

If acceptance fails, withdraw the new vhosts/service using the reviewed operator
pipeline and retain logs/backups privately. Restore the previous application
release where present; these application changes require no new migration, so do
not automatically downgrade the database or erase accounts/site welcomes.
The existing static Neocities field remains available independently. Before
public onboarding, arrange NODE06 PostgreSQL backups/restore rehearsal through
the existing operator backup path. Confirm service health plus user flows after
any rollback; a successful restart alone is insufficient.

Do not claim first deployment is complete until actual host, DNS/TLS, runtime,
migration and browser acceptance evidence have been recorded.
