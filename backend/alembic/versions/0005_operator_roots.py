"""Operator-selected Git roots on an existing registered site."""

import sqlalchemy as sa
from alembic import op

revision = "0005_operator_roots"
down_revision = "0004_verifier_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "root_sources",
        sa.Column(
            "site_id",
            sa.String(96),
            sa.ForeignKey("sites.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "owner_user_id",
            sa.String(34),
            sa.ForeignKey("users.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("origin", sa.String(512), nullable=False),
        sa.Column("repository_url", sa.String(512), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("candidate_digest", sa.String(64), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_table(
        "root_entries",
        sa.Column(
            "point_id",
            sa.String(96),
            sa.ForeignKey("points.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column(
            "site_id",
            sa.String(96),
            sa.ForeignKey("root_sources.site_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "revision_id",
            sa.String(34),
            sa.ForeignKey("point_revisions.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("lang", sa.String(80), nullable=False),
        sa.Column("content_digest", sa.String(64), nullable=False),
    )
    op.create_index("ix_root_entries_site", "root_entries", ["site_id"])
    op.execute(
        "UPDATE schema_metadata SET value = 'operator-roots-5', updated_at = now() "
        "WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_table("root_entries")
    op.drop_table("root_sources")
    op.execute(
        "UPDATE schema_metadata SET value = 'site-management-4', updated_at = now() "
        "WHERE key = 'schema'"
    )
