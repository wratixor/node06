"""Per-entrance home blocks independent of Git-owned welcome content."""

import sqlalchemy as sa
from alembic import op

revision = "0006_home_page"
down_revision = "0005_operator_roots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sites", sa.Column("home_page", sa.JSON(), nullable=True))
    op.execute(
        "UPDATE schema_metadata SET value = 'home-page-6', updated_at = now() WHERE key = 'schema'"
    )


def downgrade() -> None:
    op.drop_column("sites", "home_page")
    op.execute(
        "UPDATE schema_metadata SET value = 'operator-roots-5', updated_at = now() "
        "WHERE key = 'schema'"
    )
