"""Private account favorites, independent of subscriptions and influence."""

from alembic import op

revision = "0011_favorite_points"
down_revision = "0010_social_versions"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE favorite_points (
        user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        point_id VARCHAR(96) NOT NULL REFERENCES points(id) ON DELETE CASCADE,
        PRIMARY KEY (user_id, point_id)
    )""")


def downgrade():
    op.execute("DROP TABLE favorite_points")
