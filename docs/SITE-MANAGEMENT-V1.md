# First-party site management — P03b

Implemented locally on 22 October 2026. No backend production deployment or
production migration is implied. All paths below start with `/api/v1`.
Account/session setup is in [AUTH-V1.md](AUTH-V1.md). `/sites/` now provides the
first-party site UI; `/account/` manages the shared service account. Hosted/read-only
frame setup is in [HOSTED-WIKI-V1](HOSTED-WIKI-V1.md).
These are service-wide accounts, not Geno-Dice Wallet or Arena identities.

## Authorization

Every management route requires the first-party HTTPS session cookie. Mutations
also require the exact configured `Origin`, `Content-Type: application/json` and
`X-CSRF-Token` returned by `/me` or login. No cross-origin credential access is
enabled. Private GETs reject a foreign Origin if present. Responses, including
errors, use `Cache-Control: no-store` and frame denial.

Only `sites.owner_user_id` may manage a site. A site remains distinct from its
user and from its hostname. Origin ownership never grants authority over other
points. Session/account/owner checks run inside each DB transaction; verification
rechecks them after outbound I/O. Lock order is user → session → site → claim.
Other future mutators/importers must respect that order and the site lock when
editing its welcome. Revocation or challenge rotation during fetch prevents
activation. Network I/O holds no DB transaction open.

## Routes and payloads

| Route | Body/result |
|---|---|
| `POST /sites` | `origin`, `welcome_body`, optional `display_name`; 201 pending proof |
| `GET /me/sites?after=s_ID&limit=30` | Owned pending/active/inactive sites, sorted ID cursor, limit 1–100; `{items, next_cursor}` |
| `GET /sites/{s_id}/manage` | Private settings, welcome and claim metadata |
| `POST /sites/{s_id}/claim/renew` | `{expected_claim_id: "c_…"}`; new proof for a pending site only |
| `POST /sites/{s_id}/verify` | `{}`; active public site data after proof check |
| `PATCH /sites/{s_id}` | Complete settings payload below; returns new private settings |
| `GET /sites/{s_id}` | Existing public active-site read; pending sites return 404 |

Create and renew return `site_id`, `claim_id`, normalized `origin`,
`proof_path: "/node06-verification.txt"`, `proof_document` and `expires_at`.
Publish the exact document at that path on the claimed site, then request verify.
Only its challenge digest is stored. Private reads cannot recover the document;
if a create/renew response is lost, list/read the pending site and explicitly
renew its current challenge. Creation is not retry-idempotent: an occupied origin
returns 409, including an expired pending claim. No automatic takeover occurs.

Private settings include `id`, `origin`, `state`, `display_name`, `theme`,
`welcome_source`, `settings_revision`, `welcome_revision_id`, `welcome_body`,
`claim_id`, `claim_expires_at`, `attempt_count`. They omit nonce/digest and
credentials. Public active-site REST read retains its previous fields; the
hosted/site and read-only frame shells now receive the saved theme separately.

```json
{
  "expected_settings_revision": 1,
  "expected_welcome_revision": "v_0123456789abcdef0123456789abcdef",
  "display_name": "My garden",
  "welcome_body": "Welcome / Добро пожаловать",
  "theme": {"bg": "#10151d", "text": "#d7e0e8", "font": "mono", "radius": 8}
}
```

Both revision preconditions are required. A stale write returns 409; reload and
reconcile deliberately. Any actual settings change increments settings revision.
Changed text appends an immutable point revision; a theme/name-only edit keeps
the text revision. A no-op creates neither a revision nor an update event.
An empty theme clears overrides. Missing `display_name` resets it to null;
callers should submit the complete snapshot. Unknown fields are rejected.

Theme keys match the existing embed token allowlist: `bg/text/accent/panel/border`
are `#RGB` or `#RRGGBB`; `radius` is an integer 0–16 (not bool); `font` is
`system/serif/mono`; `density` is `normal/compact`. Null tokens are omitted.
No CSS string, stylesheet URL, script or arbitrary theme key is accepted.

Display name is at most 160 characters; welcome is 1–8192 characters and at most
32 KiB UTF-8. Site requests have a 64 KiB pre-parse body limit, including chunked
bodies. For now welcome is raw text data, not trusted rendered HTML; the future
renderer must escape/sanitize it. `md://` links are rejected until the revisioned
semantic editor is implemented. Any language or a mixture can occupy one welcome;
there are no locale variants or separate language graphs.

## Verification budgets and failures

The existing transport fetches only HTTPS port 443 and the exact proof path,
rejects redirects and non-public DNS answers, pins a public address and validates
TLS hostname/certificate. The body is at most 8 KiB. A spawned child process wraps
DNS, TLS and body reading under a total deadline, including startup time charged
to that budget. The parent terminates/reaps an overdue child; on Linux its own
alarm also limits a surviving child if the parent exits. Cleanup may add a brief
termination grace (0.5 seconds). Existing local TLS tests exercise the transport;
spawn tests exercise real process timeout/result/failure cleanup.

Migration `0004_verifier_leases` adds a small shared PostgreSQL admission table.
Multiple API workers compete atomically for fixed slots. Expired leases recover
after worker failure, and release checks lease ID to avoid deleting a successor.
All instances sharing a DB must use the same slot/deadline configuration. The
reverse proxy still owns inbound request timeouts; this budget bounds outbound
proof work, not the complete HTTP/DB request lifecycle.

Admission happens before the durable claim attempt: global overload does not
consume an attempt. A fetch failure/timeout does. Active-site verify replay
returns its public state without network I/O. Limits are deliberately configurable
initial server budgets, not product tiers or purchased influence:

| Environment variable | Default |
|---|---|
| `NODE06_SITE_CREATIONS_PER_HOUR` | 5 per account and per client IP |
| `NODE06_SITE_RENEWALS_PER_HOUR` | 5 per account |
| `NODE06_SITE_VERIFICATIONS_PER_MINUTE` | 6 per account and per client IP |
| `NODE06_CLAIM_MAX_ATTEMPTS` | 10 per challenge |
| `NODE06_VERIFIER_SECONDS` | 10 total seconds, configurable 0.1–30 |
| `NODE06_VERIFIER_SLOTS` | 2 across workers, configurable 1–8 |

Rate counters persist in PostgreSQL; they use the transport client address, not
arbitrary forwarded headers. Configure trusted proxy handling before production.
Renewal rotates the challenge ID/digest/expiry and resets attempts; the old file
ceases to work. A pending claim expires after 30 minutes.

| Status/code | Recovery |
|---|---|
| 401 `AUTH_REQUIRED` | Sign in again |
| 403 origin/CSRF/`SITE_FORBIDDEN` | Correct trusted caller, session or owner |
| 409 `SITE_CONFLICT` / `SITE_CLAIM_EXPIRED` | Reload current state; renew a pending claim if appropriate |
| 429 `AUTH_RATE_LIMITED` | Wait for `Retry-After` |
| 429 `SITE_ATTEMPTS_EXCEEDED` | Explicitly renew challenge; waiting alone does not reset it |
| 503 `VERIFIER_BUSY` | Retry later; `Retry-After: 2`, or shared slots are recovering |
| 504 `VERIFIER_TIMEOUT` | Check site availability and retry within budgets |
| 502 `PROOF_FETCH_FAILED` / 400 `PROOF_MISMATCH` | Fix the exact public proof file/TLS/DNS |
| 413 / 422 | Reduce body or correct fields; validation does not echo submitted values |

## Remaining work and rollout

This packet does not finish P03: scoped embed grants, PKCE and trusted consent
remain after the site UI/read-only hosted slice. Release/transfer/aliases/co-owners/Git welcome mode are
not exposed. Supporter notifications and revision-bound endorsements must be in
place before introducing support/votes; this packet cannot silently carry votes
to a rewritten meaning because voting does not exist yet. Git importer and the
general point editor/search still belong to P04/P05.

Apply `alembic upgrade head` to the intended environment through its operator
pipeline before running this version. Local/CI tests use disposable schemas with
0001→0002→0003→0004 and downgrade/re-upgrade. No production action is authorized
by this document. See [deployment handoff](DEPLOYMENT-HANDOFF.md).
