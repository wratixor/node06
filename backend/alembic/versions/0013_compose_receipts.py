"""Bind external publication retries across trusted windows and account changes."""

from alembic import op

revision = "0013_compose_receipts"
down_revision = "0012_social_geometry"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE compose_receipts (
        key VARCHAR(80) PRIMARY KEY,
        user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        site_id VARCHAR(34) NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
        request_digest VARCHAR(64) NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
    )""")


def downgrade():
    op.execute("DROP TABLE compose_receipts")
