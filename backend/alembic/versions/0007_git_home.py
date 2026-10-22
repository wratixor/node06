"""Git-owned home snapshots and explicit source priority."""

import sqlalchemy as sa
from alembic import op

revision = "0007_git_home"
down_revision = "0006_home_page"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("git_home_page", sa.JSON(), nullable=True))
    op.add_column(
        "sites", sa.Column("home_page_source", sa.String(16), nullable=False, server_default="auto")
    )
    op.create_check_constraint(
        "ck_sites_home_page_source", "sites", "home_page_source IN ('auto', 'git', 'ui', 'welcome')"
    )
    # An already authored UI layout is an explicit existing choice, not a default.
    op.execute(
        "UPDATE sites SET home_page_source = 'ui' "
        "WHERE home_page IS NOT NULL AND home_page::text <> 'null'"
    )
    op.execute(
        "UPDATE schema_metadata SET value = 'git-home-7', updated_at = now() WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_constraint("ck_sites_home_page_source", "sites", type_="check")
    op.drop_column("sites", "home_page_source")
    op.drop_column("sites", "git_home_page")
    op.execute(
        "UPDATE schema_metadata SET value = 'home-page-6', updated_at = now() WHERE key = 'schema'"
    )
