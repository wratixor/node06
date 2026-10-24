"""Index the immutable creation ordering used by private feed date pages."""

from alembic import op

revision = "0015_creation_feed"
down_revision = "0014_user_blocks"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        'CREATE INDEX ix_points_created_feed ON points (created_at DESC, id COLLATE "C" DESC)'
    )


def downgrade():
    op.execute("DROP INDEX ix_points_created_feed")
