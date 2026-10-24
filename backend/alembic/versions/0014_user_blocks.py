"""Explicit author blocks, separate from point reactions and T1 trust."""

from alembic import op

revision = "0014_user_blocks"
down_revision = "0013_compose_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE user_blocks (
        source_user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        PRIMARY KEY (source_user_id, target_user_id),
        CONSTRAINT ck_user_blocks_no_self CHECK (source_user_id != target_user_id)
    )""")


def downgrade():
    op.execute("DROP TABLE user_blocks")
