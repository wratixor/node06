"""Revision subscriptions, explicit ballots, durable outbox and T1 snapshots."""

from alembic import op

revision = "0010_social_versions"
down_revision = "0009_point_authoring"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        """
        CREATE TABLE subscriptions (
        user_id VARCHAR(34) NOT NULL,
        point_id VARCHAR(96) NOT NULL,
        active BOOLEAN DEFAULT 'true' NOT NULL,
        revision_id VARCHAR(34),
        content_digest VARCHAR(64) NOT NULL,
        static_body TEXT,
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
        PRIMARY KEY (user_id, point_id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(point_id) REFERENCES points (id) ON DELETE CASCADE,
        FOREIGN KEY(revision_id) REFERENCES point_revisions (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_subscriptions_point_active ON subscriptions (point_id, active)
        """
    )
    op.execute(
        """
        CREATE TABLE proposals (
        id VARCHAR(34) NOT NULL,
        point_id VARCHAR(96) NOT NULL,
        author_user_id VARCHAR(34) NOT NULL,
        base_revision_id VARCHAR(34),
        base_digest VARCHAR(64) NOT NULL,
        base_body TEXT NOT NULL,
        base_lang VARCHAR(80) NOT NULL,
        candidate_revision_id VARCHAR(34) NOT NULL,
        candidate_digest VARCHAR(64) NOT NULL,
        content JSON NOT NULL,
        citations JSON NOT NULL,
        state VARCHAR(16) DEFAULT 'open' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        closes_at TIMESTAMP WITH TIME ZONE NOT NULL,
        result JSON,
        PRIMARY KEY (id),
        CONSTRAINT ck_proposals_state CHECK (state IN ('open','adopted','retained','stale')),
        FOREIGN KEY(point_id) REFERENCES points (id) ON DELETE CASCADE,
        FOREIGN KEY(author_user_id) REFERENCES users (id) ON DELETE RESTRICT,
        FOREIGN KEY(candidate_revision_id) REFERENCES point_revisions (id) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_proposals_due ON proposals (state, closes_at)
        """
    )
    op.execute(
        """
        CREATE UNIQUE INDEX uq_proposals_open ON proposals (point_id) WHERE state = 'open'
        """
    )
    op.execute(
        """
        CREATE TABLE ballots (
        proposal_id VARCHAR(34) NOT NULL,
        user_id VARCHAR(34) NOT NULL,
        choice VARCHAR(3) NOT NULL,
        updated_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (proposal_id, user_id),
        CONSTRAINT ck_ballots_choice CHECK (choice IN ('old','new')),
        FOREIGN KEY(proposal_id) REFERENCES proposals (id) ON DELETE CASCADE,
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE social_user_state (
        user_id VARCHAR(34) NOT NULL,
        last_proposed_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (user_id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE user_trust (
        source_user_id VARCHAR(34) NOT NULL,
        target_user_id VARCHAR(34) NOT NULL,
        PRIMARY KEY (source_user_id, target_user_id),
        CONSTRAINT ck_trust_no_self CHECK (source_user_id != target_user_id),
        FOREIGN KEY(source_user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(target_user_id) REFERENCES users (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE social_events (
        seq BIGSERIAL NOT NULL,
        kind VARCHAR(40) NOT NULL,
        point_id VARCHAR(96),
        proposal_id VARCHAR(34),
        actor_user_id VARCHAR(34),
        payload JSON NOT NULL,
        public BOOLEAN DEFAULT 'false' NOT NULL,
        fanout_done BOOLEAN DEFAULT 'true' NOT NULL,
        audience_cursor VARCHAR(34) DEFAULT '' NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (seq),
        FOREIGN KEY(point_id) REFERENCES points (id) ON DELETE SET NULL,
        FOREIGN KEY(proposal_id) REFERENCES proposals (id) ON DELETE SET NULL,
        FOREIGN KEY(actor_user_id) REFERENCES users (id) ON DELETE SET NULL
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_social_events_outbox ON social_events (fanout_done, seq)
        """
    )
    op.execute(
        """
        CREATE TABLE subscription_intervals (
        id VARCHAR(34) NOT NULL,
        user_id VARCHAR(34) NOT NULL,
        point_id VARCHAR(96) NOT NULL,
        start_seq BIGINT NOT NULL,
        end_seq BIGINT,
        PRIMARY KEY (id),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(point_id) REFERENCES points (id) ON DELETE CASCADE,
        FOREIGN KEY(start_seq) REFERENCES social_events (seq) ON DELETE RESTRICT,
        FOREIGN KEY(end_seq) REFERENCES social_events (seq) ON DELETE RESTRICT
        )
        """
    )
    op.execute(
        """
        CREATE INDEX ix_subscription_audience ON subscription_intervals (point_id, user_id)
        """
    )
    op.execute(
        """
        CREATE TABLE inbox (
        user_id VARCHAR(34) NOT NULL,
        event_seq BIGINT NOT NULL,
        read_at TIMESTAMP WITH TIME ZONE,
        PRIMARY KEY (user_id, event_seq),
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(event_seq) REFERENCES social_events (seq) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE core_publications (
        point_id VARCHAR(96) NOT NULL,
        content_digest VARCHAR(64) NOT NULL,
        body TEXT NOT NULL,
        build_revision VARCHAR(128) NOT NULL,
        PRIMARY KEY (point_id),
        FOREIGN KEY(point_id) REFERENCES points (id) ON DELETE CASCADE
        )
        """
    )
    op.execute(
        """
        CREATE TABLE influence_runs (
        id VARCHAR(34) NOT NULL,
        input_digest VARCHAR(64) NOT NULL,
        data JSON NOT NULL,
        created_at TIMESTAMP WITH TIME ZONE NOT NULL,
        PRIMARY KEY (id)
        )
        """
    )
    op.execute(
        """
        CREATE TABLE support_history (
        event_seq BIGINT NOT NULL,
        user_id VARCHAR(34) NOT NULL,
        point_id VARCHAR(96) NOT NULL,
        previous_revision_id VARCHAR(34),
        previous_digest VARCHAR(64),
        revision_id VARCHAR(34),
        content_digest VARCHAR(64) NOT NULL,
        reason VARCHAR(32) NOT NULL,
        PRIMARY KEY (event_seq, user_id, point_id),
        FOREIGN KEY(event_seq) REFERENCES social_events (seq) ON DELETE RESTRICT,
        FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE,
        FOREIGN KEY(point_id) REFERENCES points (id) ON DELETE CASCADE
        )
        """
    )


def downgrade():
    op.drop_table("support_history")
    op.drop_table("influence_runs")
    op.drop_table("core_publications")
    op.drop_table("inbox")
    op.drop_table("subscription_intervals")
    op.drop_table("social_events")
    op.drop_table("user_trust")
    op.drop_table("social_user_state")
    op.drop_table("ballots")
    op.drop_table("proposals")
    op.drop_table("subscriptions")
