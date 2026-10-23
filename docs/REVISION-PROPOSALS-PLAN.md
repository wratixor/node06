# Revision subscriptions and community proposals: next implementation packet

Owner decisions recorded and clarified 23 October 2026. This revision supersedes
the earlier system-only protection, Git/community-overlay and headcount-voting proposals. This is an implementation plan, **not
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
- Decisions use **influence, never the number of people/accounts**. At scheduled
  close (72 hours by default), compare only explicit ballots submitted during
  this proposal: adopt iff `new_influence > old_influence`; equal influence retains
  the old base. Freeze the deadline when opening a proposal.
- A subscription is not a ballot. Joining may initially subscribe to the old
  version, but this does not cast an old-version vote. Existing old-version
  subscriptions also do not cast votes automatically. Nonvoters contribute zero
  to both ballot totals throughout this proposal.
- An explicit vote atomically records the user's proposal choice and creates or
  switches that user's subscription/support to the selected old/new version.
  Voting old is a real ballot even when the subscription was already old; the
  automatic old-version enrollment step before voting new is not a second ballot.
  Keep at most one current ballot per user/proposal; a switch replaces its choice,
  not an additional unit. Preserve choice/subscription audit and replay safety.
- Immediate early adoption requires explicit new-version ballots representing
  100% of **all current eligible subscribers' influence**, not only cast influence.
  The total subscribed influence must be positive. Silent subscribers do not add
  old votes to the final tally, but their uncast positive influence prevents
  early closure. A first new-version vote cannot close early if other subscribers
  still hold positive uncast influence. Zero-weight subscribers add no influence
  to either condition; zero total influence cannot auto-adopt.
- Membership, actual ballots and authoritative influence snapshot must be
  consistent at finalization. Both versions use the same snapshot/weight rules;
  neither duplicates a person's influence. Zero-weight accounts do not add weight.
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
record this as subscription history, never as an implicit proposal ballot. The
explicit vote and final selected-version subscription commit atomically.
The server sums eligible influence of explicit ballots for each version; browsers
never submit authoritative weights/totals. Account counts are informational only. Static
core and Git sources remain subscribable, but are never community proposal targets.
Recheck source protection transactionally, rather than trusting a form's disabled
button or the public origin label alone. Check unanimous early completion after
relevant committed membership/choice changes using one point-level serialization
boundary; a stale subscriber list or influence snapshot cannot prove 100% support.

Both immediate unanimous finalization and scheduled finalization are committed
mutations, not anonymous GET side effects. Use a bounded
operator/background job with a durable claim/lease and idempotent result. Close
expired proposals even when nobody opens the site. The same atomic adoption
operation handles both unanimous and scheduled closure exactly once. A base
change makes a proposal stale; never replay it against newer text. A successful adoption creates a new
immutable public revision and preserves original authorship/source separately
from proposer/editor identity. New-version supporters keep their explicit choice;
old-version subscribers remain historical/pending reconfirmation, with zero
support for new text. Influence-weighted decisions depend on the authoritative
influence calculation; there is no fallback to one-account-one-vote.

The two decision predicates are deliberately different:

```text
scheduled: I_new_explicit > I_old_explicit
immediate: I_all_subscribers > 0
           and I_new_explicit_current_subscribers == I_all_subscribers
```

All values use the same authoritative influence snapshot/eligibility and exact
agreed numerical contract. Nonvoters are absent from scheduled ballot totals;
their subscribed influence belongs only in early-consent coverage. A bare
100% share of ballots cast so far is not enough to finalize early.

## Influence dependency

The owner's correction replaces all earlier references to comparing vote counts
or requiring every account's vote. For example, one explicit new-version voter
contributing 0.6 units beats ten explicit old-version voters contributing 0.04
units each at scheduled close (0.6 > 0.4); it is not an early 100% result.
For the final tally, silent subscribers never add old-version ballot influence.
An explicit positive old-version ballot rules out early 100% new support. Silent
positive subscribed influence also blocks early consent coverage. Ten zero-weight
accounts cannot change a positive weighted result. Zero cast influence cannot
adopt through a 0/0 interpretation.

Weights must come from the agreed server-side influence model and identify a
versioned snapshot in the adoption record. This correction does not approve the
existing candidate T1 recursion, damping, per-point allocation, snapshot update
cadence or numerical representation by implication; these remain the documented
P06 model decision/validation. Do not substitute headcount while that model is
missing, invent a second unbudgeted voting currency, duplicate a person's weight
across versions, or treat a near-100% float as exact unanimity without an explicit
numerical contract. Stable old/new totals and snapshot lineage must be auditable.

Implementation sequence: build subscription/proposal/notification storage first;
provide and validate authoritative influence snapshots (P06 foundation); then
enable binding weighted finalization. This avoids a circular dependency while
keeping an unfinished mass model from silently becoming equal-count democracy.
Nonbinding previews may show an explicit influence-unavailable state, never a
fake weighted result. Git authority remains independent of community influence.

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
arrival subscription defaults old without a ballot; all silent => no adoption;
old/new explicit ballots only; atomic ballot/subscription switch; switching/revoked
session/duplicate vote; vote-close race;
new_influence>old_influence, reverse, weighted tie, zero-total; fixed closing time
and 24h/7d bounds; exactly-once
finalization/outbox with worker crash/retry; stale base and changed target pin;
all Git roots/welcome protection; source update authority and changelog;
automatic Git endorsement transfer with old/new provenance, no-op/retry/retirement;
no automatic endorsement transfer on user edits; author/site-welcome edit versus subscribe
race (theme-only settings still work; subscribed welcome text cannot bypass voting);
100% influence closure, positive old or silent subscribed influence blocking it,
zero-weight accounts
not blocking it, zero-total rejection, unequal headcount/influence majorities,
join/unsubscribe/switch versus early-close races; notification privacy/paging/read
ownership; fresh migration and
upgrade with existing P05c data. Browser acceptance must include no-site users,
mobile comparison, API conflicts and network failure/retry. Then run the existing
complete suite, packaged-wheel browser checks, build/lint/protocol and doc checks.

This packet does not silently approve a trust formula, pricing, federation,
geographic moderation or public publication of previously hidden lore. Binding
adoption requires the P06 influence dependency above; other items remain their
separate approved plan stages.
