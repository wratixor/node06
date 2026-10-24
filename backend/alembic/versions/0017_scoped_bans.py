"""Scoped publication bans and private quarantine, without account deletion."""

from alembic import op

revision = "0017_scoped_bans"
down_revision = "0016_scoped_moderation"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE moderation_bans (
        scope VARCHAR(34) NOT NULL, user_id VARCHAR(34) NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
        mode VARCHAR(16) NOT NULL CONSTRAINT ck_moderation_bans_mode
            CHECK (mode IN ('block','quarantine')),
        active BOOLEAN NOT NULL, starts_at TIMESTAMPTZ NOT NULL,
        expires_at TIMESTAMPTZ, reason TEXT NOT NULL,
        updated_by VARCHAR(34) REFERENCES users(id) ON DELETE SET NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(scope,user_id), CONSTRAINT ck_moderation_bans_time
            CHECK (expires_at IS NULL OR expires_at > starts_at))""")
    op.execute("CREATE INDEX ix_moderation_bans_user ON moderation_bans(user_id)")


def downgrade():
    op.execute("DROP TABLE moderation_bans")
