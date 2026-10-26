"""Short-lived, session-bound subscription consent, PKCE codes and grants."""

from alembic import op

revision = "0023_embed_subscriptions"
down_revision = "0022_profile_preferences"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE embed_subscriptions (
        id VARCHAR(34) PRIMARY KEY,
        site_id VARCHAR(34) NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
        parent_origin VARCHAR(512) NOT NULL, challenge VARCHAR(43) NOT NULL,
        state VARCHAR(32) NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        pending_until TIMESTAMPTZ NOT NULL,
        user_id VARCHAR(34) REFERENCES users(id) ON DELETE CASCADE,
        session_digest VARCHAR(64) REFERENCES sessions(digest) ON DELETE CASCADE,
        approved_until TIMESTAMPTZ, code_digest VARCHAR(64) UNIQUE,
        code_until TIMESTAMPTZ, token_digest VARCHAR(64) UNIQUE,
        consented BOOLEAN NOT NULL DEFAULT false, revoked BOOLEAN NOT NULL DEFAULT false
    )""")
    op.execute("CREATE INDEX ix_embed_subscriptions_user ON embed_subscriptions(user_id)")
    op.execute("CREATE INDEX ix_embed_subscriptions_pending ON embed_subscriptions(pending_until)")


def downgrade():
    op.execute("DROP TABLE embed_subscriptions")
