"""bootstrap schema metadata

Revision ID: 0001_bootstrap_schema
Revises:
Create Date: 2026-09-13
"""

import sqlalchemy as sa
from alembic import op

revision = "0001_bootstrap_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "schema_metadata",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.execute("INSERT INTO schema_metadata (key, value) VALUES ('schema', 'bootstrap-1')")


def downgrade() -> None:
    op.drop_table("schema_metadata")
