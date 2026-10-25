"""Private account pairing, scoped to link status/revocation, not profile writes."""

from alembic import op

revision = "0020_profile_links"
down_revision = "0019_git_sources"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE profile_links (
        id VARCHAR(34) PRIMARY KEY,
        user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        direction VARCHAR(8) NOT NULL CONSTRAINT ck_profile_links_direction
            CHECK (direction IN ('outbound', 'inbound')),
        peer_origin VARCHAR(512) NOT NULL,
        peer_user_id VARCHAR(34), peer_handle VARCHAR(64), remote_id VARCHAR(34),
        status VARCHAR(12) NOT NULL CONSTRAINT ck_profile_links_status
            CHECK (status IN ('pending','exchanging','active','revoked')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), expires_at TIMESTAMPTZ NOT NULL,
        invite_digest VARCHAR(64), verifier VARCHAR(64), nonce VARCHAR(64) NOT NULL,
        challenge VARCHAR(64) NOT NULL, code_digest VARCHAR(64),
        token_digest VARCHAR(64), remote_token VARCHAR(64),
        revocation_pending BOOLEAN NOT NULL DEFAULT false
    )""")
    op.execute("CREATE INDEX ix_profile_links_owner ON profile_links(user_id, created_at)")
    op.execute("CREATE UNIQUE INDEX ix_profile_links_invite ON profile_links(invite_digest)")
    op.execute("CREATE UNIQUE INDEX ix_profile_links_code ON profile_links(code_digest)")
    op.execute("CREATE UNIQUE INDEX ix_profile_links_token ON profile_links(token_digest)")


def downgrade():
    op.execute("DROP TABLE profile_links")
