"""User six-component coordinates and version-bound negative point reactions."""

from alembic import op

revision = "0012_social_geometry"
down_revision = "0011_favorite_points"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE user_geometry (
        user_id VARCHAR(34) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        coordinates JSON NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL
    )""")
    op.execute("""CREATE TABLE point_blocks (
        user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        point_id VARCHAR(96) NOT NULL REFERENCES points(id) ON DELETE CASCADE,
        revision_id VARCHAR(34) REFERENCES point_revisions(id) ON DELETE RESTRICT,
        content_digest VARCHAR(64) NOT NULL,
        static_body TEXT,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (user_id, point_id)
    )""")
    op.execute("CREATE INDEX ix_point_blocks_point ON point_blocks(point_id)")


def downgrade():
    op.execute("DROP TABLE point_blocks")
    op.execute("DROP TABLE user_geometry")
