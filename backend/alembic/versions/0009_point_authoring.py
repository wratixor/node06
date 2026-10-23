"""Explicit publication, immutable citation pins and actor-scoped replay receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0009_point_authoring"
down_revision = "0008_point_search"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "authored_points",
        sa.Column(
            "point_id",
            sa.String(96),
            sa.ForeignKey("points.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lang", sa.String(35), nullable=False),
    )
    op.create_table(
        "authored_revisions",
        sa.Column(
            "revision_id",
            sa.String(34),
            sa.ForeignKey("point_revisions.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("lang", sa.String(35), nullable=False),
        sa.Column("citations", sa.JSON(), nullable=False),
    )
    op.create_table(
        "point_operations",
        sa.Column(
            "user_id",
            sa.String(34),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("key", sa.String(80), primary_key=True),
        sa.Column("request_digest", sa.String(64), nullable=False),
        sa.Column("response", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )


def downgrade():
    op.drop_table("point_operations")
    op.drop_table("authored_revisions")
    op.drop_table("authored_points")
