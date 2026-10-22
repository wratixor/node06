import multiprocessing
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from node06_service import verifier
from node06_service.config import Settings
from node06_service.models import verifier_leases
from node06_service.site_claims import ProofFetchError
from node06_service.verifier import (
    ProofVerifier,
    VerifierBusyError,
    VerifierTimeoutError,
    fetch_in_process,
)
from sqlalchemy import select, update


# Top-level functions are importable by real spawn children on Linux and Windows.
def slow_worker(sender, _origin, _seconds):
    time.sleep(10)
    sender.close()


def returning_worker(sender, _origin, _seconds):
    sender.send((True, b"proof"))
    sender.close()


def oversize_worker(sender, _origin, _seconds):
    sender.send((True, b"x" * 8193))
    sender.close()


def failed_worker(sender, _origin, _seconds):
    sender.send((False, b""))
    sender.close()


def crashed_worker(sender, _origin, _seconds):
    sender.close()


def test_real_process_deadline_terminates_stuck_worker(monkeypatch):
    monkeypatch.setattr(verifier, "_proof_worker", slow_worker)
    existing = {p.pid for p in multiprocessing.active_children()}
    start = time.monotonic()
    with pytest.raises(VerifierTimeoutError):
        fetch_in_process("https://never-requested.example", 0.3)
    assert time.monotonic() - start < 3
    assert {p.pid for p in multiprocessing.active_children()} <= existing


@pytest.mark.parametrize(
    "worker,error",
    [
        (returning_worker, None),
        (oversize_worker, ProofFetchError),
        (failed_worker, ProofFetchError),
        (crashed_worker, VerifierTimeoutError),
    ],
)
def test_real_process_result_or_failure_is_closed(monkeypatch, worker, error):
    monkeypatch.setattr(verifier, "_proof_worker", worker)
    existing = {p.pid for p in multiprocessing.active_children()}
    if error:
        with pytest.raises(error):
            fetch_in_process("https://never-requested.example", 5)
    else:
        assert fetch_in_process("https://never-requested.example", 5) == b"proof"
    assert {p.pid for p in multiprocessing.active_children()} <= existing


def test_shared_slot_concurrency_expiry_and_stale_release(pg_database):
    settings = Settings(verifier_slots=1)
    barrier = Barrier(2)

    def acquire(_):
        barrier.wait(timeout=5)
        try:
            return ProofVerifier(pg_database, settings).acquire()
        except VerifierBusyError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(acquire, range(2)))
    assert sum(lease is not None for lease in leases) == 1
    old = next(lease for lease in leases if lease)
    with pg_database.begin() as connection:
        connection.execute(
            update(verifier_leases).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    gate = ProofVerifier(pg_database, settings)
    new = gate.acquire()
    assert new != old
    gate.release(old)
    with pytest.raises(VerifierBusyError):
        gate.acquire()
    gate.release(new)
    with pytest.raises(ProofFetchError), gate.admitted():
        raise ProofFetchError("network failed")
    with pg_database.connect() as connection:
        assert connection.execute(select(verifier_leases)).all() == []
