"""Independent bounded source polling; never delays social calculations."""

import asyncio
import logging

from sqlalchemy.exc import SQLAlchemyError

from .root_import import RootImportError
from .site_claims import SiteClaimError
from .source_service import Sources
from .verifier import ProofVerifier

logger = logging.getLogger(__name__)


async def run(app, stop):
    settings = app.state.settings.model_copy(update={"verifier_seconds": 30})
    service = Sources(app.state.database, verifier=ProofVerifier(app.state.database, settings))
    while not stop.is_set():
        try:
            await asyncio.to_thread(service.work)
        except (SQLAlchemyError, SiteClaimError, RootImportError) as exc:
            app.state.source_worker_status = {"state": "unavailable", "code": type(exc).__name__}
            logger.warning("NODE06 source worker unavailable (%s)", type(exc).__name__)
        else:
            app.state.source_worker_status = {"state": "ready"}
        try:
            await asyncio.wait_for(stop.wait(), timeout=60)
        except TimeoutError:
            pass
