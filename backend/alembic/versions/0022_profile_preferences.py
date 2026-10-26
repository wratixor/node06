"""Causal profile preferences, deletion markers and separate private-data consent."""

from alembic import op

revision = "0022_profile_preferences"
down_revision = "0021_site_author_blocks"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""CREATE TABLE profile_preference_state (
        user_id VARCHAR(34) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
        clock BIGINT NOT NULL DEFAULT 0, seeded BOOLEAN NOT NULL DEFAULT false)""")
    op.execute("""CREATE TABLE profile_preferences (
        user_id VARCHAR(34) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        kind VARCHAR(16) NOT NULL
            CHECK (kind IN ('color','favorites','subscriptions','own_points')),
        origin VARCHAR(512) NOT NULL, point_id VARCHAR(96) NOT NULL,
        value JSON NOT NULL, deleted BOOLEAN NOT NULL,
        clock BIGINT NOT NULL, writer_origin VARCHAR(512) NOT NULL,
        writer_user_id VARCHAR(34) NOT NULL, event_id VARCHAR(32) NOT NULL,
        PRIMARY KEY (user_id, kind, origin, point_id))""")
    for name, sql_type in (
        ("sync_send", "JSON NOT NULL DEFAULT '[]'"),
        ("sync_receive", "JSON NOT NULL DEFAULT '[]'"),
        ("sync_send_allowed", "JSON NOT NULL DEFAULT '[]'"),
        ("sync_receive_allowed", "JSON NOT NULL DEFAULT '[]'"),
        ("data_token_digest", "VARCHAR(64)"),
        ("remote_data_token", "VARCHAR(64)"),
        ("sync_enabled", "BOOLEAN NOT NULL DEFAULT false"),
        ("sync_local_cursor", "JSON"),
        ("sync_peer_cursor", "JSON"),
        ("sync_local_done", "BOOLEAN NOT NULL DEFAULT false"),
        ("sync_peer_done", "BOOLEAN NOT NULL DEFAULT false"),
        ("sync_next_check", "TIMESTAMPTZ NOT NULL DEFAULT now()"),
        ("sync_lease", "VARCHAR(32)"),
        ("sync_lease_until", "TIMESTAMPTZ"),
        ("sync_generation", "BIGINT NOT NULL DEFAULT 1"),
        ("sync_last_success", "TIMESTAMPTZ"),
        ("sync_error", "VARCHAR(64)"),
        ("sync_attempts", "INTEGER NOT NULL DEFAULT 0"),
    ):
        op.execute(f"ALTER TABLE profile_links ADD COLUMN {name} {sql_type}")
    op.execute(
        "CREATE UNIQUE INDEX ix_profile_links_data_token ON profile_links(data_token_digest)"
    )
    op.execute(
        "CREATE INDEX ix_profile_links_sync_due ON profile_links(sync_enabled, sync_next_check)"
    )
    op.execute("""CREATE FUNCTION node06_profile_put(
        actor VARCHAR, category VARCHAR, source VARCHAR, pid VARCHAR, body JSON,
        removed BOOLEAN, writer VARCHAR, baseline BIGINT DEFAULT NULL)
        RETURNS void LANGUAGE plpgsql AS $$
        DECLARE oldrow profile_preferences%ROWTYPE; tick BIGINT;
        BEGIN
          INSERT INTO profile_preference_state(user_id) VALUES(actor) ON CONFLICT DO NOTHING;
          SELECT clock INTO tick FROM profile_preference_state WHERE user_id=actor FOR UPDATE;
          SELECT * INTO oldrow FROM profile_preferences WHERE user_id=actor AND kind=category
              AND origin=source AND point_id=pid;
          IF FOUND AND (baseline IS NOT NULL OR
              (oldrow.value::jsonb=body::jsonb AND oldrow.deleted=removed)) THEN RETURN; END IF;
          tick := COALESCE(baseline, GREATEST(tick+1,
              floor(extract(epoch FROM clock_timestamp())*1000)::bigint*65536));
          UPDATE profile_preference_state SET clock=GREATEST(clock,tick) WHERE user_id=actor;
          INSERT INTO profile_preferences VALUES(actor,category,source,pid,body,removed,tick,
              writer,actor,replace(gen_random_uuid()::text,'-',''))
          ON CONFLICT(user_id,kind,origin,point_id) DO UPDATE SET value=excluded.value,
              deleted=excluded.deleted, clock=excluded.clock, writer_origin=excluded.writer_origin,
              writer_user_id=excluded.writer_user_id,event_id=excluded.event_id;
        END $$""")
    op.execute("""CREATE FUNCTION node06_profile_native() RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE source VARCHAR; actor VARCHAR; pid VARCHAR; body JSON; removed BOOLEAN;
        BEGIN
          source := current_setting('node06.profile_origin',true);
          IF source IS NULL OR source='' OR current_setting('node06.profile_import',true)='on'
              THEN RETURN NULL; END IF;
          IF TG_TABLE_NAME='user_geometry' THEN
            IF TG_OP='DELETE' THEN RETURN NULL; END IF;
            IF TG_OP='UPDATE' AND OLD.coordinates::jsonb=NEW.coordinates::jsonb
                THEN RETURN NULL; END IF;
            PERFORM node06_profile_put(NEW.user_id,'color','','',NEW.coordinates,false,source);
          ELSE
            IF TG_OP='DELETE' THEN actor:=OLD.user_id; pid:=OLD.point_id; removed:=true;
            ELSE actor:=NEW.user_id; pid:=NEW.point_id;
              removed:=CASE WHEN TG_TABLE_NAME='subscriptions'
                THEN NOT (to_jsonb(NEW)->>'active')::boolean ELSE false END;
            END IF;
            IF TG_TABLE_NAME='subscriptions' THEN
              IF TG_OP='UPDATE' AND OLD.active=NEW.active THEN RETURN NULL; END IF;
            END IF;
            PERFORM node06_profile_put(actor,
                CASE WHEN TG_TABLE_NAME='subscriptions' THEN 'subscriptions' ELSE 'favorites' END,
                source,pid,'{}'::json,removed,source);
          END IF;
          RETURN NULL;
        END $$""")
    for table in ("favorite_points", "subscriptions", "user_geometry"):
        op.execute(
            f"CREATE TRIGGER profile_native AFTER INSERT OR UPDATE OR DELETE ON {table} "
            "FOR EACH ROW EXECUTE FUNCTION node06_profile_native()"
        )


def downgrade():
    for table in ("favorite_points", "subscriptions", "user_geometry"):
        op.execute(f"DROP TRIGGER profile_native ON {table}")
    op.execute("DROP FUNCTION node06_profile_native()")
    op.execute(
        "DROP FUNCTION node06_profile_put("
        "VARCHAR,VARCHAR,VARCHAR,VARCHAR,JSON,BOOLEAN,VARCHAR,BIGINT)"
    )
    op.execute("DROP INDEX ix_profile_links_data_token")
    op.execute("DROP INDEX ix_profile_links_sync_due")
    for name in (
        "sync_send",
        "sync_receive",
        "sync_send_allowed",
        "sync_receive_allowed",
        "data_token_digest",
        "remote_data_token",
        "sync_enabled",
        "sync_local_cursor",
        "sync_peer_cursor",
        "sync_local_done",
        "sync_peer_done",
        "sync_next_check",
        "sync_lease",
        "sync_lease_until",
        "sync_generation",
        "sync_last_success",
        "sync_error",
        "sync_attempts",
    ):
        op.execute(f"ALTER TABLE profile_links DROP COLUMN {name}")
    op.execute("DROP TABLE profile_preferences")
    op.execute("DROP TABLE profile_preference_state")
