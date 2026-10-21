# Shared account sessions — P03a

Implemented slice: first-party account registration, login, logout, global session
revocation and recovery. P03 as a whole is still incomplete: authenticated site
management, the verification executor budget, scoped embed grants/PKCE and trusted
action confirmation remain next work. There is no Wallet or Arena account link.

## Account and recovery contract

An account is common to the service, independent of the site used to discover it.
Handles are 3–64 ASCII lowercase letters, digits, hyphen or underscore, starting
with a letter/digit. Passwords are 12–128 characters, at most 512 UTF-8 bytes.
Registration returns `201` with `account_created=true`, the user ID/handle and a
single newly generated recovery code; it does not log the user in. A conflict
returns `409 ACCOUNT_CONFLICT`, never an account-created result.

Owner decision, 21 October 2026: recovery uses an emergency code rather than
email/SMS. Save the code when shown after registration. Recovery requires handle,
code and a new password; it atomically changes the password, replaces the code
and revokes every existing session. Only the new code is returned. A replay or
concurrent second use of the old code fails. The code cannot be read back from
the service; `/me` does not return it. Losing both the password and recovery code
has no implemented automated recovery path. Store the replacement code safely.

The database stores an explicit Argon2id password hash (64 MiB, time cost 3,
parallelism 1), SHA-256 recovery digest and SHA-256 session digest. Random secrets
contain 256 bits of entropy. No password or session cookie is returned in JSON.
The recovery code is deliberately returned once in the successful registration/
recovery response. Validation errors are redacted instead of reflecting inputs.
Argon2 dependency: [argon2-cffi documentation](https://argon2-cffi.readthedocs.io/en/stable/howto.html).

## HTTP and browser boundary

Configure `NODE06_MANAGEMENT_ORIGIN` as one exact HTTPS origin without a trailing
slash. Mutation calls require that exact browser Origin; missing, `null` and
foreign origins fail. Password-bearing calls require JSON. Authentication calls
reject plain HTTP even when an Origin header is forged. Configure the HTTPS
reverse proxy/Uvicorn trusted forwarded-header sources explicitly; do not accept
arbitrary public proxy headers. No CORS credentials are enabled.

| Route (prefix `/api/v1`) | Contract |
| --- | --- |
| `POST /auth/register` | `{handle,password}`; creates account and returns recovery code once |
| `POST /auth/login` | `{handle,password}`; sets cookie, returns identity + CSRF value |
| `GET /me` | Current identity + CSRF value, or 401; never global bearer/recovery code |
| `DELETE /auth/session` | Current browser logout, exact Origin + `X-CSRF-Token` |
| `DELETE /auth/sessions` | Revoke all of this account's sessions, same protections |
| `POST /auth/recover` | `{handle,password,recovery_code}`; new password/code, revoke sessions |

Cookie: `__Host-node06-session`, Secure, HttpOnly, SameSite=Strict, Path=/,
no Domain. It is never given to an embedding parent. Login rotates a presented
session for the same account. A disabled account or expired/revoked session fails
on the next check. These first-party sessions are not embed grants and do not
promise third-party-cookie SSO. Sensitive responses use no-store and deny framing.
The CSRF value is a domain-separated digest of the session secret; it cannot be
used as the session cookie or as a global bearer credential.

`/account/` is a small first-party RU management entry with separate self-hosted
JS/CSS, strict CSP, register/login/recover forms and logout controls. Errors retain
form values. Registration prefills the login name. Recovery displays a fresh code
and switches back to login. If login returns success but `/me` fails, the UI reports
that the browser did not establish a session. No credentials go into localStorage,
query strings or bridge messages. Browser code never reads the HttpOnly cookie.

## Limits and operations

- Actual auth request bodies, including chunked ones, are capped at 16 KiB before
  parsing. Edge/server body-read timeouts remain required against slow uploads.
- PostgreSQL UPSERT counters apply across workers. Defaults/configuration:
  `NODE06_REGISTRATION_PER_HOUR=3` per peer IP;
  `NODE06_LOGIN_PER_MINUTE=10` per IP and
  `NODE06_ACCOUNT_LOGIN_PER_MINUTE=10` per handle. Recovery uses independent
  counters with the same limits. Keys are digests, never raw IP/handle strings.
- `NODE06_SESSION_HOURS=24` (configurable 1–720) controls session lifetime.
- A per-process two-slot guard bounds concurrent Argon2 work to roughly 128 MiB
  plus overhead; excess work returns `503 AUTH_BUSY`. It is a memory guard, not
  a global rate limiter. Local three-run measurement: 137–140 ms/hash on 21 Oct.
- Rate limits return `429 AUTH_RATE_LIMITED` and conservative `Retry-After`.
  Peer IP means the ASGI client address after the server's trusted proxy policy,
  not an arbitrary client-supplied X-Forwarded-For header.
- Migration `0003_account_sessions` adds credentials, sessions and auth counters;
  existing P02 placeholder principals gain no password/recovery automatically.
  Upgrade before starting this revision; no production migration was performed.
- Before public alpha: operator account block/revoke procedure, periodic pruning
  of expired sessions/idle auth counters, measured worker budget and real browser/
  proxy acceptance. There is no claim/settings HTTP write API in this slice.

## Validation

Use the disposable PostgreSQL procedure in `backend/README.md`. The shared fixture
upgrades `0001` → `0002` → head through psycopg for each isolated schema. Auth cases
cover conflict/failure responses, session cookie flags/rotation/expiry/revocation,
origin/CSRF, disabled accounts, recovery/code races, redacted validation, chunked
body limits and shared atomic counters. The previous migration downgrade/re-upgrade
test now also exercises `0003`.

Local Chromium HTTPS smoke at 390px verified registration, one-time code display,
login and secure cookie, recovery and session invalidation in a second tab,
logout-all, no page errors and no horizontal overflow. This is not a physical
mobile device or Neocities embed test. A simulated login success without a cookie
also produces an explicit session-establishment failure; this is not proof of
every real browser cookie policy. Registration conflicts retain input values.
Local full suite: 63 passed, including real PostgreSQL migrations/races. Ruff,
offline migration SQL, static build (51 roots), JS syntax and P00 protocol passed.
Existing test-client dependencies emit two
deprecation warnings; functional tests pass and dependency migration is deferred.
