from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)

metadata = MetaData()

schema_metadata = Table(
    "schema_metadata",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("value", Text, nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

users = Table(
    "users",
    metadata,
    Column("id", String(34), primary_key=True),
    Column("handle", String(64), nullable=False, unique=True),
    Column("state", String(16), nullable=False, server_default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("state IN ('active', 'disabled')", name="ck_users_state"),
)

points = Table(
    "points",
    metadata,
    Column("id", String(96), primary_key=True),
    Column("origin", String(16), nullable=False),
    Column("author_user_id", ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("current_revision_id", String(34), nullable=True),
    Column("lifecycle", String(16), nullable=False, server_default="active"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column(
        "content_updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    Column(
        "last_interaction_at", DateTime(timezone=True), nullable=False, server_default=func.now()
    ),
    CheckConstraint("origin IN ('root', 'user', 'site')", name="ck_points_origin"),
    CheckConstraint("lifecycle IN ('active', 'inactive', 'retired')", name="ck_points_lifecycle"),
    ForeignKeyConstraint(
        ["current_revision_id"],
        ["point_revisions.id"],
        name="fk_points_current_revision",
        use_alter=True,
        ondelete="SET NULL",
    ),
)

point_revisions = Table(
    "point_revisions",
    metadata,
    Column("id", String(34), primary_key=True),
    Column("point_id", ForeignKey("points.id", ondelete="CASCADE"), nullable=False),
    Column("body", Text, nullable=False),
    Column("declared_links", JSON, nullable=False, server_default="[]"),
    Column("editor_user_id", ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)
Index("ix_point_revisions_point_created", point_revisions.c.point_id, point_revisions.c.created_at)

sites = Table(
    "sites",
    metadata,
    Column("id", ForeignKey("points.id", ondelete="RESTRICT"), primary_key=True),
    Column("owner_user_id", ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("claimed_origin", String(512), nullable=False),
    Column("primary_origin", String(512), nullable=True),
    Column("state", String(16), nullable=False, server_default="pending"),
    Column("welcome_source", String(16), nullable=False, server_default="ui"),
    Column("home_page", JSON, nullable=True),
    Column("git_home_page", JSON, nullable=True),
    Column("home_page_source", String(16), nullable=False, server_default="auto"),
    CheckConstraint(
        "home_page_source IN ('auto', 'git', 'ui', 'welcome')", name="ck_sites_home_page_source"
    ),
    Column("settings_revision", Integer, nullable=False, server_default="1"),
    Column("display_name", String(160), nullable=True),
    Column("theme", JSON, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    Column("verified_at", DateTime(timezone=True), nullable=True),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("state IN ('pending', 'active', 'inactive')", name="ck_sites_state"),
    CheckConstraint("welcome_source IN ('ui', 'git')", name="ck_sites_welcome_source"),
)
Index("ix_sites_owner", sites.c.owner_user_id)
Index(
    "uq_sites_claimed_origin_live",
    sites.c.claimed_origin,
    unique=True,
    postgresql_where=sites.c.state.in_(("pending", "active")),
    sqlite_where=sites.c.state.in_(("pending", "active")),
)
Index(
    "ix_sites_primary_origin",
    sites.c.primary_origin,
    unique=True,
    postgresql_where=sites.c.primary_origin.is_not(None),
)

site_members = Table(
    "site_members",
    metadata,
    Column("site_id", ForeignKey("sites.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role", String(16), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("role IN ('owner', 'editor')", name="ck_site_members_role"),
)
Index("ix_site_members_user", site_members.c.user_id)

site_claims = Table(
    "site_claims",
    metadata,
    Column("id", String(34), primary_key=True),
    Column("site_id", ForeignKey("sites.id", ondelete="CASCADE"), nullable=False),
    Column("origin", String(512), nullable=False),
    Column("challenge_digest", String(64), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("verified_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("site_id", "origin", name="uq_site_claim_site_origin"),
)
Index("ix_site_claim_origin", site_claims.c.origin)

point_edges = Table(
    "point_edges",
    metadata,
    Column("point_a", ForeignKey("points.id", ondelete="CASCADE"), primary_key=True),
    Column("point_b", ForeignKey("points.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    CheckConstraint("point_a < point_b", name="ck_point_edges_canonical_order"),
)
Index("ix_point_edges_reverse", point_edges.c.point_b, point_edges.c.point_a)

edge_claims = Table(
    "edge_claims",
    metadata,
    Column("id", String(34), primary_key=True),
    Column("point_a", String(96), nullable=False),
    Column("point_b", String(96), nullable=False),
    Column("claim_kind", String(24), nullable=False),
    Column("claim_ref", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    ForeignKeyConstraint(
        ["point_a", "point_b"], ["point_edges.point_a", "point_edges.point_b"], ondelete="CASCADE"
    ),
    UniqueConstraint(
        "point_a", "point_b", "claim_kind", "claim_ref", name="uq_edge_claim_provenance"
    ),
    CheckConstraint("point_a < point_b", name="ck_edge_claims_canonical_order"),
)

events = Table(
    "events",
    metadata,
    Column(
        "seq", BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    ),
    Column("operation_id", String(34), nullable=False),
    Column("kind", String(48), nullable=False),
    Column("actor_user_id", ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    Column("site_id", ForeignKey("sites.id", ondelete="SET NULL"), nullable=True),
    Column("point_id", ForeignKey("points.id", ondelete="SET NULL"), nullable=True),
    Column("payload", JSON, nullable=False, server_default="{}"),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
    UniqueConstraint("operation_id", "kind", "point_id", name="uq_event_operation_kind_point"),
)
Index("ix_events_created", events.c.created_at, events.c.seq)

account_credentials = Table(
    "account_credentials",
    metadata,
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("password_hash", Text, nullable=False),
    Column("recovery_digest", String(64), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

sessions = Table(
    "sessions",
    metadata,
    Column("digest", String(64), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)
Index("ix_sessions_user", sessions.c.user_id)
Index("ix_sessions_expiry", sessions.c.expires_at)

auth_limits = Table(
    "auth_limits",
    metadata,
    Column("key", String(64), primary_key=True),
    Column("count", Integer, nullable=False),
    Column("resets_at", DateTime(timezone=True), nullable=False),
)
Index("ix_auth_limits_reset", auth_limits.c.resets_at)

verifier_leases = Table(
    "verifier_leases",
    metadata,
    Column("slot", Integer, primary_key=True),
    Column("lease_id", String(32), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)


root_sources = Table(
    "root_sources",
    metadata,
    Column("site_id", ForeignKey("sites.id", ondelete="RESTRICT"), primary_key=True),
    Column("owner_user_id", ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
    Column("origin", String(512), nullable=False),
    Column("repository_url", String(512), nullable=False),
    Column("commit_sha", String(40), nullable=False),
    Column("candidate_digest", String(64), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)

root_entries = Table(
    "root_entries",
    metadata,
    Column("point_id", ForeignKey("points.id", ondelete="RESTRICT"), primary_key=True),
    Column("site_id", ForeignKey("root_sources.site_id", ondelete="RESTRICT"), nullable=False),
    Column("revision_id", ForeignKey("point_revisions.id", ondelete="RESTRICT"), nullable=False),
    Column("lang", String(80), nullable=False),
    Column("content_digest", String(64), nullable=False),
)
Index("ix_root_entries_site", root_entries.c.site_id)
