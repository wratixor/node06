"""Permanent content tombstones, retaining point/revision identities."""

from alembic import op

revision = "0018_content_purge"
down_revision = "0017_scoped_bans"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE point_tombstones (
        point_id VARCHAR(96) PRIMARY KEY REFERENCES points(id) ON DELETE RESTRICT,
        hidden_since TIMESTAMPTZ NOT NULL, purged_at TIMESTAMPTZ NOT NULL)""")
    op.execute("""CREATE INDEX ix_authored_citations_purge
        ON authored_revisions USING gin ((citations::jsonb))""")
    op.execute("""CREATE INDEX ix_proposal_citations_purge
        ON proposals USING gin ((citations::jsonb))""")
    op.execute("""CREATE FUNCTION node06_purge_guard() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF EXISTS (SELECT 1 FROM point_tombstones WHERE point_id = NEW.point_id) THEN
            IF TG_TABLE_NAME = 'point_revisions' THEN
              IF TG_OP = 'INSERT' OR NEW.body <> '' OR NEW.search_text <> ''
                 OR NEW.declared_links::jsonb <> '[]'::jsonb THEN
                RAISE EXCEPTION 'POINT_PURGED' USING ERRCODE = '23514';
              END IF;
            ELSIF NEW.body <> '' THEN
              RAISE EXCEPTION 'POINT_PURGED' USING ERRCODE = '23514';
            END IF;
          END IF;
          RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER guard_purged_revisions BEFORE INSERT OR UPDATE
        ON point_revisions FOR EACH ROW EXECUTE FUNCTION node06_purge_guard()""")
    op.execute("""CREATE TRIGGER guard_purged_core BEFORE INSERT OR UPDATE
        ON core_publications FOR EACH ROW EXECUTE FUNCTION node06_purge_guard()""")
    op.execute("""CREATE FUNCTION node06_purged_point_guard() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
          IF EXISTS (SELECT 1 FROM point_tombstones WHERE point_id = NEW.id)
             AND (NEW.lifecycle <> 'retired'
                  OR NEW.current_revision_id IS DISTINCT FROM OLD.current_revision_id) THEN
            RAISE EXCEPTION 'POINT_PURGED' USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END $$""")
    op.execute("""CREATE TRIGGER guard_purged_points BEFORE UPDATE ON points
        FOR EACH ROW EXECUTE FUNCTION node06_purged_point_guard()""")


def downgrade():
    from sqlalchemy import text

    if op.get_bind().scalar(text("SELECT count(*) FROM point_tombstones")):
        raise RuntimeError("Purged content is irreversible; retain tombstones on rollback")
    op.execute("DROP TRIGGER guard_purged_points ON points")
    op.execute("DROP FUNCTION node06_purged_point_guard()")
    op.execute("DROP TRIGGER guard_purged_core ON core_publications")
    op.execute("DROP TRIGGER guard_purged_revisions ON point_revisions")
    op.execute("DROP FUNCTION node06_purge_guard()")
    op.execute("DROP INDEX ix_proposal_citations_purge")
    op.execute("DROP INDEX ix_authored_citations_purge")
    op.execute("DROP TABLE point_tombstones")
