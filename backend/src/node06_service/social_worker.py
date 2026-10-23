"""Bounded background work. Durable state survives process restarts."""

import asyncio
import logging
from datetime import UTC, datetime

from sqlalchemy.exc import SQLAlchemyError

from .influence import InfluenceUnavailable
from .public_points import PublicPointError, PublicPoints
from .social import Social

logger = logging.getLogger(__name__)


async def run(app, stop):
    while not stop.is_set():
        bundle = getattr(app.state, "hosted_bundle", None)
        public = PublicPoints(
            app.state.database,
            roots=bundle.roots if bundle else (),
            build_revision=app.state.settings.build_revision,
        )
        try:
            await asyncio.to_thread(Social(public).work)
        except (SQLAlchemyError, InfluenceUnavailable, PublicPointError) as exc:
            # Never log SQL parameters, DSNs, cookies or an exception's raw message.
            app.state.social_worker_status = {"state": "unavailable", "code": type(exc).__name__}
            logger.warning("NODE06 social worker unavailable (%s)", type(exc).__name__)
        else:
            app.state.social_worker_status = {
                "state": "ready",
                "last_success": datetime.now(UTC).isoformat(),
            }
        try:
            await asyncio.wait_for(stop.wait(), timeout=30)
        except TimeoutError:
            pass
