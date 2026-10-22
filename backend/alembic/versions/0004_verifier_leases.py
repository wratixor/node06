"""Distributed admission slots for the bounded site verifier."""

import sqlalchemy as sa
from alembic import op

revision = "0004_verifier_leases"
down_revision = "0003_account_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "verifier_leases",
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("lease_id", sa.String(32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("slot"),
    )
    op.execute(
        "UPDATE schema_metadata SET value = 'site-management-4', updated_at = now() "
        "WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_table("verifier_leases")
    op.execute(
        "UPDATE schema_metadata SET value = 'account-sessions-3', updated_at = now() "
        "WHERE key = 'schema'"
    )
