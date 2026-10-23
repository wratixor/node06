# Revision subscriptions and community proposals: next implementation packet

Owner decisions recorded 23 October 2026. This is an implementation plan, **not
implemented runtime behavior**. P05c authoring is described in
[POINT-AUTHORING-V1.md](POINT-AUTHORING-V1.md).

## Accepted product rules

- Account scope is the local instance; a site is not an account. Users without
  sites can create points, subscribe and propose edits. No cross-server influence.
- Semantic links do not subscribe or endorse anything automatically.
- Subscription supports a particular version. Editing the base never silently
  transfers old support. A user explicitly chooses the changed version.
- Any registered user may submit one proposal for any one point in a rolling
  24 hours across this server. Rejected validation/retries must not consume a
  second proposal or bypass the successful-proposal budget.
- Roots describing the system are protected from community replacement. Protection
  must be explicit, rather than equating every `origin=root` with system policy:
  game/lore repository roots are not automatically protected system descriptions.
- Existing subscribers receive durable private notifications and a personal feed
  entry with the proposal. Show base and candidate side by side or as a safely
  escaped diff. The proposed body remains a separate version until adoption.
- Everyone can participate, including newly arriving subscribers. During voting,
  joining starts on the old/base version; switching to the candidate is explicit.
  One user contributes at most one current choice for this point/proposal.
- At voting close count old versus new support. Adopt iff new > old; equality
  retains the old base. Do not accept early on a transient majority. No automatic
  replacement of a point with no participants.
- Approved time bounds are 24 hours through 7 days. Activity-based selection is
  not specified yet. Start with an explicit fixed operator duration inside those
  bounds; freeze the selected closing time when a proposal is opened. Do not
  implement an undocumented adaptive formula or sliding deadline.

## Storage and transaction design

Add version subscription state `(user_id, point_id, endorsed_revision/digest)`;
keep history of deliberate choices. Static text needs an immutable snapshot or
real persisted revision, never an invented v_ ID. Keep plain follow-only versus
support separate in the UI if both are eventually offered; do not silently make
one action grant a second kind of weight.

Proposal rows need point ID, immutable base revision/digest, candidate body/lang/
reference pins, author, created/close time and state. Suggested states: open,
adopted, retained, stale, withdrawn. Initially allow only one open proposal per
point with a database uniqueness constraint, so the agreed two-version vote is
not accidentally turned into unspecified multi-candidate voting. Explain a
conflict to the user, keep their draft and do not spend their daily slot.

The rolling daily limit must be stored/checked under the active user lock in the
same transaction that commits a successful proposal. The generic transport rate
limit is not this budget. Actor-scoped idempotency should reuse P05c's discipline
but namespace operation fingerprints/routes to avoid receipt collisions.

Subscribe, switch and finalize must serialize on the point/proposal and recheck
active session, current base, protected status and closing time. No switches at
or after close. Enroll new participants on old before allowing an explicit switch;
record this as an auditable transition even if both changes share a transaction.
The server counts actual current choices; browsers never submit totals. Static
core and Git baselines need the same race-safe snapshot identity.

Finalize is a committed mutation, not an anonymous GET side effect. Use a bounded
operator/background job with a durable claim/lease and idempotent result. Close
expired proposals even when nobody opens the site. A base change makes a proposal
stale; never replay it against newer text. A successful adoption creates a new
immutable public revision and preserves original authorship/source separately
from proposer/editor identity. New-version supporters keep their explicit choice;
old-version subscribers remain historical/pending reconfirmation, with zero
support for new text. No trust/mass calculation is implied by vote counts.

## Git and protected roots

Record system protection explicitly in the root manifest/operator configuration;
root points that explain policy cannot be replaced via the vote API. Validate
unknown/contradictory protection declarations before publishing.

Keep accepted repository content as a source baseline and community adoption as
an independently versioned overlay. Operator imports must not erase adopted
community text or manufacture endorsement. Define and test how a later Git
baseline change is presented (source update needing reconciliation), rather than
changing `points.current_revision_id` so an imported entry fails its own accepted-
revision visibility guard. Source owner/origin revocation must still hide content;
an overlay cannot bypass that boundary. Site welcome/home settings and mutable
post text also remain separate authorities.

Do this integration before enabling automatic adoption on imported roots; the
user requested game/lore roots too, not just newly authored p_ points. A temporary
user-only prototype must be labelled as such and not presented as the full rule.

## Durable notifications and feed

Use transactionally inserted outbox/notification records, uniquely keyed by
recipient + proposal/event kind. Required notifications: new proposal, adopted/
retained/stale outcome, changed subscribed meaning. Subscriber fanout must be
bounded/resumable with a stable recipient snapshot/cursor; a popular point cannot
make a write transaction allocate an unbounded recipient list. Delivery retry
cannot duplicate inbox entries. Mark-read is owner-only and never used as proof
of endorsement. Do not expose one user's private subscription/inbox list through
public profile or bridge.

A personal feed may use the same notification records, with durable private
cursors. Existing `events.seq` allocation is not commit order, so do not assume
`seq > last_seen` alone is a reliable outbox consumer. Use lease/undelivered rows
or a separate commit-safe cursor design. No email, SMS or external messages.

## UI and acceptance

Add first-party point actions: subscribe to displayed version, propose change,
read old/new comparison, explicitly switch support, see close time/outcome,
reconfirm after replacement, and open private inbox/feed. Public embeds can read
proposal status but still hand authenticated actions to a trusted first-party
page until scoped embed auth is implemented. Escape both diff sides; malicious
Markdown/HTML must not become executable. Keep drafts on errors and show stale
base/target conflicts without silently replacing text or votes.

Required real PostgreSQL cases: same actor/different points daily race; 24-hour
boundary; replay/conflicting receipt; two users/same point proposal race; new
arrival defaults old; switching/revoked session/duplicate vote; vote-close race;
new>old, old>new, tie, empty; fixed closing time and 24h/7d bounds; exactly-once
finalization/outbox with worker crash/retry; stale base and changed target pin;
protected system roots; Git overlay versus update/revocation; no endorsement
transfer; notification privacy/paging/read ownership; fresh migration and
upgrade with existing P05c data. Browser acceptance must include no-site users,
mobile comparison, API conflicts and network failure/retry. Then run the existing
complete suite, packaged-wheel browser checks, build/lint/protocol and doc checks.

This packet does not add trust propagation, pricing, federation, geographic
moderation or public publication of previously hidden lore. Those remain their
separate approved plan stages.
