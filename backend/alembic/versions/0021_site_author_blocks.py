"""Personal author blocks local to one site; server trust remains server-local."""

from alembic import op

revision = "0021_site_author_blocks"
down_revision = "0020_profile_links"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE site_user_blocks (
        site_id VARCHAR(96) NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
        source_user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        target_user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        PRIMARY KEY (site_id, source_user_id, target_user_id),
        CONSTRAINT ck_site_user_blocks_no_self CHECK (source_user_id != target_user_id)
    )""")
    op.execute(
        """CREATE INDEX ix_site_user_blocks_owner
        ON site_user_blocks(source_user_id, site_id, target_user_id)"""
    )


def downgrade():
    op.execute("DROP TABLE site_user_blocks")
