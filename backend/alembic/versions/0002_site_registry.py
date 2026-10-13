"""site registry and shared directory primitives

Revision ID: 0002_site_registry
Revises: 0001_bootstrap_schema
Create Date: 2026-09-15
"""

import sqlalchemy as sa
from alembic import op

revision = "0002_site_registry"
down_revision = "0001_bootstrap_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(length=34), nullable=False),
        sa.Column("handle", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("state IN ('active', 'disabled')", name="ck_users_state"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("handle"),
    )
    op.create_table(
        "points",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("origin", sa.String(length=16), nullable=False),
        sa.Column("author_user_id", sa.String(length=34), nullable=True),
        sa.Column("current_revision_id", sa.String(length=34), nullable=True),
        sa.Column("lifecycle", sa.String(length=16), server_default="active", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "content_updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "last_interaction_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("origin IN ('root', 'user', 'site')", name="ck_points_origin"),
        sa.CheckConstraint(
            "lifecycle IN ('active', 'inactive', 'retired')", name="ck_points_lifecycle"
        ),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "point_revisions",
        sa.Column("id", sa.String(length=34), nullable=False),
        sa.Column("point_id", sa.String(length=96), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "declared_links", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False
        ),
        sa.Column("editor_user_id", sa.String(length=34), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["editor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["point_id"], ["points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_point_revisions_point_created", "point_revisions", ["point_id", "created_at"]
    )
    op.create_foreign_key(
        "fk_points_current_revision",
        "points",
        "point_revisions",
        ["current_revision_id"],
        ["id"],
        ondelete="SET NULL",
        use_alter=True,
    )
    op.create_table(
        "sites",
        sa.Column("id", sa.String(length=96), nullable=False),
        sa.Column("owner_user_id", sa.String(length=34), nullable=False),
        sa.Column("claimed_origin", sa.String(length=512), nullable=False),
        sa.Column("primary_origin", sa.String(length=512), nullable=True),
        sa.Column("state", sa.String(length=16), server_default="pending", nullable=False),
        sa.Column("welcome_source", sa.String(length=16), server_default="ui", nullable=False),
        sa.Column("settings_revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("display_name", sa.String(length=160), nullable=True),
        sa.Column("theme", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("state IN ('pending', 'active', 'inactive')", name="ck_sites_state"),
        sa.CheckConstraint("welcome_source IN ('ui', 'git')", name="ck_sites_welcome_source"),
        sa.ForeignKeyConstraint(["id"], ["points.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sites_owner", "sites", ["owner_user_id"])
    op.create_index(
        "ix_sites_primary_origin",
        "sites",
        ["primary_origin"],
        unique=True,
        postgresql_where=sa.text("primary_origin IS NOT NULL"),
    )
    op.create_index(
        "uq_sites_claimed_origin_live",
        "sites",
        ["claimed_origin"],
        unique=True,
        postgresql_where=sa.text("state IN ('pending', 'active')"),
    )
    op.create_table(
        "site_members",
        sa.Column("site_id", sa.String(length=96), nullable=False),
        sa.Column("user_id", sa.String(length=34), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("role IN ('owner', 'editor')", name="ck_site_members_role"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("site_id", "user_id"),
    )
    op.create_index("ix_site_members_user", "site_members", ["user_id"])
    op.create_table(
        "site_claims",
        sa.Column("id", sa.String(length=34), nullable=False),
        sa.Column("site_id", sa.String(length=96), nullable=False),
        sa.Column("origin", sa.String(length=512), nullable=False),
        sa.Column("challenge_digest", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("site_id", "origin", name="uq_site_claim_site_origin"),
    )
    op.create_index("ix_site_claim_origin", "site_claims", ["origin"])
    op.create_table(
        "point_edges",
        sa.Column("point_a", sa.String(length=96), nullable=False),
        sa.Column("point_b", sa.String(length=96), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("point_a < point_b", name="ck_point_edges_canonical_order"),
        sa.ForeignKeyConstraint(["point_a"], ["points.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["point_b"], ["points.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("point_a", "point_b"),
    )
    op.create_index("ix_point_edges_reverse", "point_edges", ["point_b", "point_a"])
    op.create_table(
        "edge_claims",
        sa.Column("id", sa.String(length=34), nullable=False),
        sa.Column("point_a", sa.String(length=96), nullable=False),
        sa.Column("point_b", sa.String(length=96), nullable=False),
        sa.Column("claim_kind", sa.String(length=24), nullable=False),
        sa.Column("claim_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("point_a < point_b", name="ck_edge_claims_canonical_order"),
        sa.ForeignKeyConstraint(
            ["point_a", "point_b"],
            ["point_edges.point_a", "point_edges.point_b"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "point_a", "point_b", "claim_kind", "claim_ref", name="uq_edge_claim_provenance"
        ),
    )
    op.create_table(
        "events",
        sa.Column("seq", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("operation_id", sa.String(length=34), nullable=False),
        sa.Column("kind", sa.String(length=48), nullable=False),
        sa.Column("actor_user_id", sa.String(length=34), nullable=True),
        sa.Column("site_id", sa.String(length=96), nullable=True),
        sa.Column("point_id", sa.String(length=96), nullable=True),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'::json"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["point_id"], ["points.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["site_id"], ["sites.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("seq"),
        sa.UniqueConstraint(
            "operation_id", "kind", "point_id", name="uq_event_operation_kind_point"
        ),
    )
    op.create_index("ix_events_created", "events", ["created_at", "seq"])

    # all-sites is a core projection needed by P02 before the general root importer (P04).
    op.execute(
        """
        INSERT INTO points (id, origin, lifecycle)
        VALUES ('all-sites', 'root', 'active')
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO point_revisions (id, point_id, body, declared_links)
        VALUES (
            'v_00000000000000000000000000000000',
            'all-sites',
            'All sites / Все сайты',
            '[]'::json
        )
        ON CONFLICT (id) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE points
        SET current_revision_id = 'v_00000000000000000000000000000000'
        WHERE id = 'all-sites' AND current_revision_id IS NULL
        """
    )
    op.execute(
        "UPDATE schema_metadata "
        "SET value = 'site-registry-2', updated_at = now() "
        "WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_index("ix_events_created", table_name="events")
    op.drop_table("events")
    op.drop_table("edge_claims")
    op.drop_index("ix_point_edges_reverse", table_name="point_edges")
    op.drop_table("point_edges")
    op.drop_index("ix_site_claim_origin", table_name="site_claims")
    op.drop_table("site_claims")
    op.drop_index("ix_site_members_user", table_name="site_members")
    op.drop_table("site_members")
    op.drop_index("uq_sites_claimed_origin_live", table_name="sites")
    op.drop_index("ix_sites_primary_origin", table_name="sites")
    op.drop_index("ix_sites_owner", table_name="sites")
    op.drop_table("sites")
    op.drop_constraint("fk_points_current_revision", "points", type_="foreignkey")
    op.drop_index("ix_point_revisions_point_created", table_name="point_revisions")
    op.drop_table("point_revisions")
    op.drop_table("points")
    op.drop_table("users")
    op.execute(
        "UPDATE schema_metadata SET value = 'bootstrap-1', updated_at = now() WHERE key = 'schema'"
    )
