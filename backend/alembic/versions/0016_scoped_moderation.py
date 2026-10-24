"""Scoped moderation, deduplicated reports and reversible visibility; no purge."""

from alembic import op

revision = "0016_scoped_moderation"
down_revision = "0015_creation_feed"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE moderation_roles (
        scope VARCHAR(34) NOT NULL, user_id VARCHAR(34) NOT NULL
        REFERENCES users(id) ON DELETE CASCADE,
        role VARCHAR(16) NOT NULL CHECK (role IN ('admin','moderator')),
        PRIMARY KEY(scope,user_id))""")
    op.execute("""CREATE TABLE point_hides (
        scope VARCHAR(34) NOT NULL, point_id VARCHAR(96) NOT NULL, active BOOLEAN NOT NULL,
        hidden_since TIMESTAMPTZ, updated_by VARCHAR(34) REFERENCES users(id) ON DELETE SET NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(scope,point_id))""")
    op.execute("""CREATE TABLE moderation_cases (
        scope VARCHAR(34) NOT NULL, point_id VARCHAR(96) NOT NULL,
        status VARCHAR(16) NOT NULL DEFAULT 'open' CHECK(status IN ('open','closed')),
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(), PRIMARY KEY(scope,point_id))""")
    op.execute("""CREATE TABLE moderation_reports (
        scope VARCHAR(34) NOT NULL, point_id VARCHAR(96) NOT NULL,
        reporter_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        reason TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY(scope,point_id,reporter_id), FOREIGN KEY(scope,point_id)
        REFERENCES moderation_cases(scope,point_id) ON DELETE CASCADE)""")
    op.execute("""CREATE TABLE moderation_audit (
        id VARCHAR(34) PRIMARY KEY, scope VARCHAR(34) NOT NULL,
        actor_id VARCHAR(34) REFERENCES users(id) ON DELETE SET NULL, action VARCHAR(16) NOT NULL,
        target VARCHAR(96) NOT NULL, detail JSON NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now())""")


def downgrade():
    for name in (
        "moderation_audit",
        "moderation_reports",
        "moderation_cases",
        "point_hides",
        "moderation_roles",
    ):
        op.execute("DROP TABLE " + name)
