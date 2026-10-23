# Embedded drafts and trusted publication

This packet adds a creation editor over static/Neocities and full-iframe maps.
It does **not** grant authenticated API access to an external parent. Anonymous
bridge capabilities remain read-only; `embed_auth` stays unimplemented.

## User flow

1. New related post opens a modal on the current map. The draft frame uses
   `/compose/v1/{site_id}/` on the configured embed origin. The exact source
   point is read again and its current revision/digest becomes the initial link.
2. Text and tag search work without cookies or login. Account favorites and own
   post editing remain on the first-party editor; they are not exposed to frames.
3. **Check and publish** explicitly opens a trusted management window. The user
   sees the immutable plain text, selected point IDs, registered site origin and
   publishing account. Login/registration stays in trusted top-level account UI.
4. Only **Publish as me** posts the reviewed content with session/CSRF protection.
   An acknowledgement sends the public point ID back; the modal closes and the
   original map opens that point. No credentials, profile or private state cross
   windows. Merely opening the editor or confirmation page publishes nothing.

Management-host maps retain their same-origin modal and direct publication.
External own-point editing, private favorites and broad scoped embed grants are
future work. This bounded creation flow does not claim to implement all P03.
If popups are blocked, the draft stays on screen and offers an explicit retry.

## Boundaries and replay

- Draft document checks active verified site and exact embed host. Its CSP allows
  that registered origin, the embed host (for the full-frame shell), and the
  trusted management host for owner previews.
  A requested parent origin must be exactly one of those. No wildcard origins.
- The trusted confirmation document is DENY / `frame-ancestors 'none'`. Account
  pages keep the same policy. Private API routes remain absent on the embed host.
- Two separate random per-opening channels bind parent/frame and frame/popup.
  Every message validates exact source window, observed origin, protocol and
  channel. Only the draft frame talks to the trusted popup. Parent receives only
  close state or the resulting public point ID; it cannot submit a changed payload.
- `node06-publish/1`: popup `ready`; frame `draft` with site, immutable Content
  payload and random operation key; popup `published` (public ID) or `rejected`
  (definite error). Once displayed, a different payload/key cannot replace it.
- POST `/editor/confirm/{site_id}/` reuses normal Content validation, rate/body
  limits, session/CSRF, public-link pins and atomic authoring. Migration
  **0013_compose_receipts** binds the operation key globally to actor, site and
  exact request digest in the same transaction as the normal publication receipt.
  Different actor/site/text replay conflicts, including across popup reloads or
  closes. A failed transaction stores neither publication nor binding.
- Lost response: retry the same frozen operation/key. Pending text/links remain
  locked. Account/conflict errors preserve the receipt for recovery; definite
  validation errors return to editing. No automatic new-key retry.
- Closing an external dirty draft asks inside the parent modal, avoiding browser
  restrictions on cross-origin iframe `confirm()`. While the approval window is
  open, editor close waits; close that window first. Discarding after an uncertain
  write warns that publication may already have succeeded.
- No draft or session is stored in parent storage, URLs or public logs. Random
  channels/operation keys are correlation IDs, not account credentials.

## Static point opening

A static copy hydrates an explicit `p`/`open` point using `point.read`, then missing
neighbors in bounded groups of four, at most50. It keeps local seeds when present;
new points use labelled display-only fallback until social coordinates exist.
Remote HTML is copied through a fixed tag/attribute allowlist, never executed.
Fresh posts therefore open on Neocities immediately, without a static rebuild.
The existing public API's neighbor cursor/truncation remains a bounded projection,
not a full server graph. Failure retains static roots and labels unavailable reads.

## Compact social profile

`/community/` groups own points, subscriptions, blocks, favorites, inbox, trust and Git news
in keyboard-operable tabs, with a filter over the currently loaded rows. Color is
a separate tab with six color-only inputs. Only one panel is shown at a time;
old/new version comparison opens in a separate collapsible block when a point
is selected. Tab URLs use fragments (`#points`, `#subscriptions`, `#blocks`,
`#favorites`, `#inbox`, `#trust`, `#news`, `#color`); reload and browser Back/Forward
restore the panel. The old `#my-color` link remains an alias. Filtering is hidden
for color/trust, where it would not describe the form. Subscriptions have direct
unsubscribe, blocks have unblock, favorites have remove. Neutral unsubscribe and
explicit negative block retain their distinct semantics. Reaction list previews
are additive private API fields; unavailable points remain identifiable.

Account, profile, sites and first-party editor share one server-rendered menu:
wiki, profile, sites, new point, sign-in/security. The current page is marked with
`aria-current`; links navigate in the same tab except editor sign-in, which
keeps a separate tab to preserve the draft (other map editor links still target
the trusted top-level page when framed). Header styles and link definitions live in
`personal_ui.py`, so these pages cannot drift independently. The account page
retains its one-time recovery code and session controls; authentication and
private APIs remain first-party only. The anonymous compose frame continues to
hide the header; this navigation adds no embed authentication capability.

## Acceptance and release

Run the full disposable PostgreSQL suite, Ruff/format, build/protocol/JS checks,
and packaged-wheel local HTTPS browser fixture. Browser acceptance covers related
root pins, no popup on opening the draft, canceled close, trusted review,
response-loss replay, return to static point, sanitization and compact panels.
Test wrong host/parent, pending/revoked site, CSRF/body limits, actor/text replay,
and normal authoring regression. Online upgrade from0012 and downgrade/re-upgrade
are required. Production needs backup-first migration0013 through normal deploy;
no new Nginx API exception, cookie policy or privileged installer is required.
Local acceptance is not live Neocities publication proof.

Rollback: an older application can ignore0013 while its table remains. Do not
remove receipt bindings while an external publication has an unknown outcome;
keep database backup/receipts for reconciliation. Downgrade drops only this new
binding table, never points, revisions or existing actor-scoped operation receipts.

Source acceptance, 23 October 2026: full disposable PostgreSQL suite239 passed;
after strengthening the populated migration/receipt fixtures, both focused checks
passed again. Online0012→0013 and downgrade/re-upgrade preserved published text,
revision and normal operation receipt. Installed-wheel HTTPS Chromium passed
with three controlled origins: static root linking, dirty-close cancellation,
trusted review and response-loss replay, return to the static point, nested
full-frame editor, compact panels/filter/keyboard controls and no embed cookies.
Ruff/format, static51-root build, JavaScript syntax and protocol checks passed.
These are local source checks, not production publication claims.
