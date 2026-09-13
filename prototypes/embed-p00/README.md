# P00: two-origin iframe prototype

This is a local, synthetic transport proof. It is not backend code, a deployable
SDK, authentication, or evidence that Neocities accepts the final deployment.

Run it from the repository root:

```bash
python3 prototypes/embed-p00/serve.py
node prototypes/embed-p00/tests/protocol.test.mjs
```

Open `http://127.0.0.1:4273/parent/`. The parent uses an intentionally
Neocities-like CSP: it cannot fetch the other origin, but can frame it. The
iframe at `http://localhost:4274/embed/` has its own origin and accepts only the
exact registered parent origin. It performs a fresh `postMessage` handshake on
every load, checks source/origin/channel/schema, exposes a small typed read/theme
surface, and sends write intents to an explicit `AUTH_CONFIRMATION_REQUIRED`
boundary. The parent never receives a credential.

Use the controls to request a point, apply a valid theme, reject a CSS-like
payload, reject an unimplemented write intent, and reload the frame. The Node
test covers envelope and theme validation; browser checks still need to cover
the real handshake/CSP result.

The prototype intentionally does not cover PKCE, persistent sessions, actual
API calls, site verification, real Neocities origins, or full-wiki rendering.
