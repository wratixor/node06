# Revision subscriptions and community proposals: next implementation packet

Owner decisions recorded and clarified 23 October 2026. This revision supersedes
the earlier system-only protection and Git/community-overlay proposal. This is an implementation plan, **not
implemented runtime behavior**. P05c authoring is described in
[POINT-AUTHORING-V1.md](POINT-AUTHORING-V1.md).

## Accepted product rules

- Account scope is the local instance; a site is not an account. Users without
  sites can create points, subscribe and propose edits. No cross-server influence.
- Semantic links do not subscribe or endorse anything automatically.
- For user-authored content, subscription supports a particular version. Changing
  its base never automatically transfers support; the user chooses the new text.
  Git-owned points are the explicitly approved exception: accepted Git updates
  automatically transfer their current active support to the new source version.
  Preserve the old endorsement and transfer provenance in history.
- Any registered user may submit one proposal for any one point in a rolling
  24 hours across this server. Rejected validation/retries must not consume a
  second proposal or bypass the successful-proposal budget.
- Every Git-owned point is protected from community proposals and replacement,
  including game/lore content, the built core and Git-managed welcome content.
  Source authority belongs to the authorized repository publisher, not vote totals.
  System-owned directory/state remains protected by its existing operator authority.
- Authors may edit their own non-Git points directly while there are no active
  subscribers. With active subscribers, even the original author must propose a
  change and use voting; direct write APIs cannot bypass this rule. This includes
  the owner-authored text of a UI-managed site welcome. Site settings/theme/domain
  ownership remain owner-managed; changing those is not permission to replace a
  subscribed welcome's meaning.
- Existing subscribers receive durable private notifications and a personal feed
  entry with the proposal. Show base and candidate side by side or as a safely
  escaped diff. The proposed body remains a separate version until adoption.
- Everyone can participate, including newly arriving subscribers. During voting,
  joining starts on the old/base version; switching to the candidate is explicit.
  One user contributes at most one current choice for this point/proposal.
- Default voting duration is 72 hours. At scheduled close, adopt iff new > old;
  equality retains the old base. Freeze the deadline when opening a proposal.
- Early adoption is allowed immediately when **all current active subscribers**
  explicitly support the candidate. No minimum waiting period applies to this
  unanimous exception. A transient simple majority is not enough. At least one
  subscriber is required: zero is not unanimity. One subscriber's explicit support
  is sufficient if that subscriber is the entire current subscriber set; the owner
  approved no extra quorum. Joining/unsubscribing/voting and closing must serialize
  so a concurrent new old-version subscriber cannot be omitted from this count.
- General configurable scheduled duration bounds remain 24 hours through 7 days;
  they do not delay unanimous early adoption. Activity-based selection is future
  policy, not an invented adaptive formula or sliding deadline.

## Storage and transaction design

Add version subscription state `(user_id, point_id, endorsed_revision/digest)`;
keep history of deliberate choices. Static text needs an immutable snapshot or
real persisted revision, never an invented v_ ID. Keep plain follow-only versus
support separate in the UI if both are eventually offered; do not silently make
one action grant a second kind of weight.

Proposal rows need point ID, immutable base revision/digest, candidate body/lang/
reference pins, author, created/close time and state. Suggested states: open,
adopted, retained, stale, withdrawn. Allow only one open proposal per
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
core and Git sources remain subscribable, but are never community proposal targets.
Recheck source protection transactionally, rather than trusting a form's disabled
button or the public origin label alone. Check unanimous early completion after
relevant committed membership/choice changes using one point-level serialization
boundary; a stale initial list of subscribers cannot prove unanimity.

Both immediate unanimous finalization and scheduled finalization are committed
mutations, not anonymous GET side effects. Use a bounded
operator/background job with a durable claim/lease and idempotent result. Close
expired proposals even when nobody opens the site. The same atomic adoption
operation handles both unanimous and scheduled closure exactly once. A base
change makes a proposal stale; never replay it against newer text. A successful adoption creates a new
immutable public revision and preserves original authorship/source separately
from proposer/editor identity. New-version supporters keep their explicit choice;
old-version subscribers remain historical/pending reconfirmation, with zero
support for new text. No trust/mass calculation is implied by vote counts.

## Git and protected roots

All repository-sourced content is protected, not only descriptions of system
policy. This is an authority boundary derived from verified source ownership:
built core and accepted Git entries, including a Git-managed site welcome, cannot
receive community replacement proposals. A caller cannot clear protection by
changing request fields, language, source alias or subscriber count. A site owner
without accepted source authority does not gain Git-publisher powers by owning
a neighboring entrance. Ordinary user points linked to Git content stay ordinary
user points; protection does not spread along graph edges.

An accepted Git publication directly replaces its current source text. There is
no community vote and **no community overlay over Git content**. Repository
publishing remains constrained by the existing owner/origin/provenance checks;
a vote never grants repository write access or changes server authorization.
In the product view the new Git version becomes the normal current knowledge.
This does not authorize destruction/falsification of stored revision history.

Git updates automatically carry active subscriptions/support forward to the new
accepted version, an owner-approved exception to user-version reconfirmation.
Store the prior endorsement, old/new revision/digest, accepted source commit and
an explicit `git-source-update` reason in the support history, so a source update
is not misrepresented as a user's fresh explicit vote. It must not create extra
users, duplicate support units or support for a retired/missing point. Preserve
unsubscribe state and any unrelated user-authored point's endorsement unchanged.
No-op reimports must not transfer twice or create duplicate news. Static builds
also need durable old/new snapshot identity before automatic support transfer;
do not invent DB revision IDs or silently mutate content on an anonymous GET.

Publish the Git change as a changelog/news entry, rather than asking each
subscriber to approve or sending a community voting request. Keep source SHA and
changed public point IDs; never leak unpublished blobs/credentials. Changes to
site settings or user points are not Git updates merely because they share a
transaction or are deployed by the same operator. Source retirement/revocation
still hides invalid content and does not create support for another point.

Git source text, user posts, site settings and system directory state remain
separate authorities. The older proposed baseline/community-overlay model is
withdrawn by the owner's later decision; do not implement it for Git roots.

## Durable notifications and feed

Use transactionally inserted outbox/notification records, uniquely keyed by
recipient + proposal/event kind. Required notifications: new proposal, adopted/
retained/stale outcome, changed subscribed user-authored meaning. Git source
updates use the changelog path above and do not require personal reconfirmation. Subscriber fanout must be
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

Add first-party point actions: subscribe to displayed version, propose a change
on eligible non-Git user/site-welcome points,
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
all Git roots/welcome protection; source update authority and changelog;
automatic Git endorsement transfer with old/new provenance, no-op/retry/retirement;
no automatic endorsement transfer on user edits; author/site-welcome edit versus subscribe
race (theme-only settings still work; subscribed welcome text cannot bypass voting); 100% immediate closure with one/many subscribers, zero-subscriber rejection,
join/unsubscribe/switch versus early-close races; notification privacy/paging/read ownership; fresh migration and
upgrade with existing P05c data. Browser acceptance must include no-site users,
mobile comparison, API conflicts and network failure/retry. Then run the existing
complete suite, packaged-wheel browser checks, build/lint/protocol and doc checks.

This packet does not add trust propagation, pricing, federation, geographic
moderation or public publication of previously hidden lore. Those remain their
separate approved plan stages.
