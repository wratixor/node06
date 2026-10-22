"""Bounded public point search with a simple-dictionary GIN index."""

import sqlalchemy as sa
from alembic import op

revision = "0008_point_search"
down_revision = "0007_git_home"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "point_revisions", sa.Column("search_text", sa.Text(), nullable=False, server_default="")
    )
    if op.get_context().as_sql:
        # Locale-independent Python casefold cannot be reproduced by SQL lower().
        # Diagnostic SQL remains generatable, but must fail closed if applied.
        op.execute(
            "DO $$ BEGIN RAISE EXCEPTION "
            "'Unicode search backfill requires online Alembic upgrade'; END $$"
        )
    else:
        connection = op.get_bind()
        revisions = sa.table(
            "point_revisions",
            sa.column("id", sa.String()),
            sa.column("body", sa.Text()),
            sa.column("search_text", sa.Text()),
        )
        rows = connection.execute(sa.select(revisions.c.id, revisions.c.body)).yield_per(100)
        for row in rows:
            connection.execute(
                revisions.update()
                .where(revisions.c.id == row.id)
                .values(search_text=row.body.casefold())
            )
    op.create_index(
        "ix_point_revisions_search_simple",
        "point_revisions",
        [sa.text("to_tsvector('simple'::regconfig, search_text)")],
        postgresql_using="gin",
    )
    op.execute(
        "UPDATE schema_metadata SET value = 'point-search-8', updated_at = now() "
        "WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_index("ix_point_revisions_search_simple", table_name="point_revisions")
    op.drop_column("point_revisions", "search_text")
    op.execute(
        "UPDATE schema_metadata SET value = 'git-home-7', updated_at = now() WHERE key = 'schema'"
    )
