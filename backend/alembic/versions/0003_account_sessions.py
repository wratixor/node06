"""Shared accounts, opaque sessions and durable authentication limits."""

import sqlalchemy as sa
from alembic import op

revision = "0003_account_sessions"
down_revision = "0002_site_registry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "account_credentials",
        sa.Column("user_id", sa.String(34), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("recovery_digest", sa.String(64), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("user_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_table(
        "sessions",
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("user_id", sa.String(34), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("digest"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_sessions_user", "sessions", ["user_id"])
    op.create_index("ix_sessions_expiry", "sessions", ["expires_at"])
    op.create_table(
        "auth_limits",
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.Column("resets_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_auth_limits_reset", "auth_limits", ["resets_at"])
    op.execute(
        "UPDATE schema_metadata SET value = 'account-sessions-3', updated_at = now() "
        "WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_index("ix_auth_limits_reset", table_name="auth_limits")
    op.drop_table("auth_limits")
    op.drop_index("ix_sessions_expiry", table_name="sessions")
    op.drop_index("ix_sessions_user", table_name="sessions")
    op.drop_table("sessions")
    op.drop_table("account_credentials")
    op.execute(
        "UPDATE schema_metadata SET value = 'site-registry-2', updated_at = now() "
        "WHERE key = 'schema'"
    )
