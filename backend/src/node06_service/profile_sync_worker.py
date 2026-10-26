"""Fair bounded polling; generation checks and expiring leases cover restarts/races."""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError

from .models import profile_links, users
from .profile_links import ProfileLinks
from .profile_peer import exchange
from .profile_sync import ProfileSync
from .public_points import PublicPointError, PublicPoints
from .site_claims import SiteClaimError

logger = logging.getLogger(__name__)


def work(app):
    db, settings = app.state.database, app.state.settings
    with db.connect() as c:
        due = c.execute(
            select(profile_links.c.user_id, profile_links.c.id)
            .join(users, users.c.id == profile_links.c.user_id)
            .where(
                profile_links.c.direction == "outbound",
                or_(
                    profile_links.c.revocation_pending.is_(True),
                    (
                        (profile_links.c.status == "active")
                        & profile_links.c.sync_enabled.is_(True)
                        & profile_links.c.remote_data_token.is_not(None)
                        & (profile_links.c.expires_at > datetime.now(UTC))
                    ),
                ),
                profile_links.c.sync_next_check <= datetime.now(UTC),
                users.c.state == "active",
                or_(
                    profile_links.c.sync_lease_until.is_(None),
                    profile_links.c.sync_lease_until <= datetime.now(UTC),
                ),
            )
            .order_by(profile_links.c.sync_next_check, profile_links.c.id)
            .limit(4)
        ).all()
    transport = getattr(app.state, "profile_link_transport", None)
    if transport is None:

        def transport(origin, operation, fields):
            return exchange(db, settings, origin, operation, fields)

    bundle = getattr(app.state, "hosted_bundle", None)
    for uid, lid in due:
        with db.connect() as c:
            pending = c.scalar(
                select(profile_links.c.revocation_pending).where(profile_links.c.id == lid)
            )
        if pending:
            try:
                ProfileLinks(db, settings.management_origin, transport).revoke(uid, lid)
            except (PublicPointError, SiteClaimError, SQLAlchemyError) as exc:
                logger.warning("NODE06 profile revoke retry (%s)", type(exc).__name__)
            finally:
                with db.begin() as c:
                    c.execute(
                        update(profile_links)
                        .where(profile_links.c.id == lid)
                        .values(sync_next_check=datetime.now(UTC) + timedelta(minutes=5))
                    )
            continue
        public = PublicPoints(
            db, roots=bundle.roots if bundle else (), build_revision=settings.build_revision
        )
        try:
            ProfileSync(
                public, settings.management_origin, transport, seconds=settings.verifier_seconds
            ).step(uid, lid)
        except (PublicPointError, SiteClaimError, SQLAlchemyError) as exc:
            # Back off failures before lease acquisition too, avoiding starvation.
            with db.begin() as c:
                c.execute(
                    update(profile_links)
                    .where(
                        profile_links.c.id == lid,
                        profile_links.c.sync_next_check <= datetime.now(UTC),
                        profile_links.c.sync_lease.is_(None),
                    )
                    .values(
                        sync_next_check=datetime.now(UTC) + timedelta(minutes=5),
                        sync_error="PROFILE_SYNC_UNAVAILABLE",
                    )
                )
            logger.warning("NODE06 profile sync retry (%s)", type(exc).__name__)


async def run(app, stop):
    while not stop.is_set():
        try:
            await asyncio.to_thread(work, app)
        except SQLAlchemyError:
            logger.warning("NODE06 profile sync database unavailable")
        try:
            await asyncio.wait_for(stop.wait(), timeout=2)
        except TimeoutError:
            pass
