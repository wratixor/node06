"""Owner-confirmed public GitHub sources and bounded private previews."""

from alembic import op

revision = "0019_git_sources"
down_revision = "0018_content_purge"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE git_sources (
        site_id VARCHAR(96) PRIMARY KEY REFERENCES sites(id) ON DELETE RESTRICT,
        owner_user_id VARCHAR(96) NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
        origin VARCHAR(512) NOT NULL,
        generation VARCHAR(32) NOT NULL,
        repository VARCHAR(256) NOT NULL, branch VARCHAR(128) NOT NULL,
        policy VARCHAR(16) NOT NULL CHECK (policy IN ('manual', 'auto')),
        proof_digest VARCHAR(64) NOT NULL, proof_expires_at TIMESTAMPTZ NOT NULL,
        repository_id BIGINT, repository_owner_id BIGINT,
        preview_id VARCHAR(32), candidate JSON, preview_base JSON,
        preview_expires_at TIMESTAMPTZ,
        accepted_preview_id VARCHAR(32), receipt JSON,
        last_attempt_at TIMESTAMPTZ, next_check_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        last_error VARCHAR(64))""")
    op.execute("CREATE INDEX ix_git_sources_due ON git_sources(policy, next_check_at)")


def downgrade():
    op.execute("DROP TABLE git_sources")
