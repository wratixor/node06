"""Hard process deadline around DNS + pinned HTTPS + bounded response read."""

from __future__ import annotations

import multiprocessing
import os
import signal
import time
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert

from .config import Settings
from .db import Database
from .models import verifier_leases
from .site_claims import MAX_PROOF_BYTES, ProofFetchError, SiteClaimError, fetch_proof


class VerifierBusyError(SiteClaimError):
    code = "VERIFIER_BUSY"


class VerifierTimeoutError(ProofFetchError):
    code = "VERIFIER_TIMEOUT"


def _deadline_exit(_signal, _frame):
    os._exit(124)


def _proof_worker(sender, origin: str, seconds: float) -> None:
    # Linux: also terminate a slow DNS/body operation if the API worker dies.
    if hasattr(signal, "setitimer"):
        signal.signal(signal.SIGALRM, _deadline_exit)
        signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        body = fetch_proof(origin, timeout=min(seconds, 5.0))
        sender.send((True, body))
    except (SiteClaimError, OSError, ValueError):
        sender.send((False, b""))
    finally:
        sender.close()


def fetch_in_process(origin: str, seconds: float) -> bytes:
    context = multiprocessing.get_context("spawn")
    receiver, sender = context.Pipe(duplex=False)
    process = context.Process(target=_proof_worker, args=(sender, origin, seconds), daemon=True)
    deadline = time.monotonic() + seconds
    try:
        try:
            process.start()
        except (OSError, RuntimeError):
            raise VerifierBusyError("Unable to start the site verifier. Retry later.") from None
        sender.close()
        if not receiver.poll(max(0, deadline - time.monotonic())):
            raise VerifierTimeoutError("Site proof check exceeded its total deadline.")
        try:
            ok, body = receiver.recv()
        except EOFError:
            raise VerifierTimeoutError(
                "Site proof worker ended before returning a result."
            ) from None
        if time.monotonic() > deadline:
            raise VerifierTimeoutError("Site proof check exceeded its total deadline.")
        if not ok or len(body) > MAX_PROOF_BYTES:
            raise ProofFetchError("Unable to retrieve the verification file.")
        return body
    finally:
        receiver.close()
        sender.close()
        if process.pid is not None:
            if process.is_alive():
                process.terminate()
            process.join(timeout=0.5)
            if process.is_alive():
                process.kill()
                process.join()
            process.close()


class ProofVerifier:
    def __init__(self, database: Database, settings: Settings):
        self.database = database
        self.settings = settings

    def acquire(self) -> str:
        lease_id = uuid4().hex
        now = datetime.now(UTC)
        expiry = now + timedelta(seconds=self.settings.verifier_seconds + 5)
        with self.database.begin() as connection:
            for slot in range(self.settings.verifier_slots):
                statement = (
                    insert(verifier_leases)
                    .values(slot=slot, lease_id=lease_id, expires_at=expiry)
                    .on_conflict_do_update(
                        index_elements=[verifier_leases.c.slot],
                        set_={"lease_id": lease_id, "expires_at": expiry},
                        where=verifier_leases.c.expires_at <= now,
                    )
                    .returning(verifier_leases.c.lease_id)
                )
                if connection.execute(statement).scalar_one_or_none():
                    return lease_id
        raise VerifierBusyError("All verifier slots are busy. Retry later.")

    def release(self, lease_id: str) -> None:
        with self.database.begin() as connection:
            connection.execute(
                delete(verifier_leases).where(verifier_leases.c.lease_id == lease_id)
            )

    def __call__(self, origin: str) -> bytes:
        with self.admitted() as fetch:
            return fetch(origin)

    @contextmanager
    def admitted(self):
        lease_id = self.acquire()
        deadline = time.monotonic() + self.settings.verifier_seconds

        def fetch(origin: str) -> bytes:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise VerifierTimeoutError("Site proof check exceeded its total deadline.")
            return fetch_in_process(origin, remaining)

        try:
            yield fetch
        finally:
            self.release(lease_id)
