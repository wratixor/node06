"""Authenticated owner HTTP flows and races against real migrated PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from node06_service.auth import SESSION_COOKIE, AuthService
from node06_service.config import Settings
from node06_service.main import create_app
from node06_service.models import events, point_edges, point_revisions, site_claims, sites
from node06_service.site_registry import SiteConflictError, SiteRegistry
from node06_service.verifier import ProofVerifier, VerifierTimeoutError
from sqlalchemy import func, select, update

ORIGIN = "https://manage.example"
PASSWORD = "a-long-test-password"


@pytest.fixture
def manager(pg_database):
    settings = Settings(
        management_origin=ORIGIN,
        registration_per_hour=100,
        site_creations_per_hour=100,
        site_verifications_per_minute=100,
    )
    app = create_app(settings)
    app.state.database = pg_database
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        created = client.post(
            "/api/v1/auth/register",
            json={
                "handle": "alice",
                "password": PASSWORD,
            },
        ).json()
        login = client.post(
            "/api/v1/auth/login",
            json={
                "handle": "alice",
                "password": PASSWORD,
            },
        )
        assert login.status_code == 200
        client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
        yield SimpleNamespace(
            client=client,
            app=app,
            user=created["user_id"],
            token=client.cookies[SESSION_COOKIE],
            auth=AuthService(pg_database, settings),
        )


def create(manager, origin="https://garden.example"):
    response = manager.client.post(
        "/api/v1/sites",
        json={
            "origin": origin,
            "display_name": "Garden",
            "welcome_body": "Точка сайта / Site point",
        },
    )
    assert response.status_code == 201, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def state(manager, site):
    response = manager.client.get(f"/api/v1/sites/{site['site_id']}/manage")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    return response.json()


def settings_payload(current, **overrides):
    return {
        "expected_settings_revision": current["settings_revision"],
        "expected_welcome_revision": current["welcome_revision_id"],
        "display_name": current["display_name"],
        "welcome_body": current["welcome_body"],
        "theme": current["theme"],
        **overrides,
    }


def test_owner_create_list_private_pending_verify_and_public_read(
    manager, pg_database, monkeypatch
):
    site = create(manager)
    create(manager, "https://second.example")
    client = manager.client
    assert client.get(f"/api/v1/sites/{site['site_id']}").status_code == 404
    first = client.get("/api/v1/me/sites?limit=1").json()
    assert len(first["items"]) == 1
    second = client.get(f"/api/v1/me/sites?limit=1&after={first['next_cursor']}").json()
    assert len(second["items"]) == 1 and second["next_cursor"] is None
    assert first["items"][0]["id"] != second["items"][0]["id"]
    assert "nonce=" not in str(first) and "challenge_digest" not in str(first)
    calls = []

    def fetch(origin, _seconds):
        calls.append(origin)
        return site["proof_document"].encode()

    monkeypatch.setattr("node06_service.verifier.fetch_in_process", fetch)
    url = f"/api/v1/sites/{site['site_id']}/verify"
    active = client.post(url, json={})
    assert active.status_code == 200, active.text
    assert active.json()["state"] == "active"
    assert client.post(url, json={}).json() == active.json()
    assert calls == [site["origin"]]
    public = client.get(f"/api/v1/sites/{site['site_id']}")
    assert public.json() == active.json()
    assert "claim_id" not in public.text and "nonce=" not in public.text
    current = state(manager, site)
    edited = client.patch(
        f"/api/v1/sites/{site['site_id']}",
        json=settings_payload(current, welcome_body="An active site's new meaning"),
    )
    assert edited.status_code == 200
    assert (
        client.get(f"/api/v1/sites/{site['site_id']}").json()["welcome_body"]
        == "An active site's new meaning"
    )
    with pg_database.connect() as connection:
        assert connection.execute(select(func.count()).select_from(point_edges)).scalar_one() == 1


def test_csrf_origin_https_cookie_and_ownership_boundaries(manager, monkeypatch):
    site = create(manager)
    client = manager.client
    path = f"/api/v1/sites/{site['site_id']}"
    current = state(manager, site)
    payload = settings_payload(current, welcome_body="Changed")
    for method, url, body in [
        ("POST", "/api/v1/sites", {"origin": "https://new.example", "welcome_body": "Hi"}),
        ("PATCH", path, payload),
        ("POST", path + "/verify", {}),
        ("POST", path + "/claim/renew", {"expected_claim_id": site["claim_id"]}),
    ]:
        for bad_headers in (
            {"Origin": "https://foreign.example"},
            {"Origin": "null"},
            {"X-CSRF-Token": "wrong"},
        ):
            response = client.request(method, url, json=body, headers=bad_headers)
            assert response.status_code == 403, response.text
        assert client.request(method, "http://manage.example" + url, json=body).status_code == 403
    assert (
        client.get(path + "/manage", headers={"Origin": "https://foreign.example"}).status_code
        == 403
    )
    monkeypatch.setattr(
        "node06_service.verifier.fetch_in_process",
        lambda *_: pytest.fail("Forbidden caller must not fetch proof"),
    )
    client.cookies.clear()
    assert client.get(path + "/manage").status_code == 401
    assert client.post(path + "/verify", json={}).status_code == 401
    client.post("/api/v1/auth/register", json={"handle": "other", "password": PASSWORD})
    login = client.post("/api/v1/auth/login", json={"handle": "other", "password": PASSWORD})
    client.headers["X-CSRF-Token"] = login.json()["csrf_token"]
    for method, suffix, body in [
        ("GET", "/manage", None),
        ("PATCH", "", payload),
        ("POST", "/verify", {}),
        ("POST", "/claim/renew", {"expected_claim_id": site["claim_id"]}),
    ]:
        assert client.request(method, path + suffix, json=body).status_code == 403
    assert client.get("/api/v1/me/sites").json()["items"] == []
    assert state_for_owner(manager, site, current["welcome_body"])


def state_for_owner(manager, site, expected):
    # Internal read confirms failed writes did not change the owner's content.
    result = SiteRegistry(manager.app.state.database).managed_site(site["site_id"], manager.user)
    return result["welcome_body"] == expected


def test_settings_preconditions_immutable_history_noop_and_theme(manager, pg_database):
    site = create(manager)
    original = state(manager, site)
    path = f"/api/v1/sites/{site['site_id']}"
    payload = settings_payload(
        original, welcome_body="New meaning", theme={"bg": "#123", "font": "mono"}
    )
    changed = manager.client.patch(path, json=payload)
    assert changed.status_code == 200, changed.text
    current = changed.json()
    assert current["settings_revision"] == 2
    assert current["welcome_revision_id"] != original["welcome_revision_id"]
    assert current["theme"] == {"bg": "#123", "font": "mono"}
    assert manager.client.patch(path, json=payload).status_code == 409
    assert manager.client.patch(path, json=settings_payload(current)).json() == current
    theme_only = manager.client.patch(
        path, json=settings_payload(current, theme={"radius": 8})
    ).json()
    assert theme_only["settings_revision"] == 3
    assert theme_only["welcome_revision_id"] == current["welcome_revision_id"]
    with pg_database.connect() as connection:
        bodies = (
            connection.execute(
                select(point_revisions.c.body).where(point_revisions.c.point_id == site["site_id"])
            )
            .scalars()
            .all()
        )
        assert sorted(bodies) == sorted([original["welcome_body"], "New meaning"])
        updates = (
            connection.execute(
                select(events.c.payload).where(events.c.kind == "site_settings_updated")
            )
            .scalars()
            .all()
        )
        assert len(updates) == 2
        assert all("New meaning" not in str(payload) for payload in updates)


def test_simultaneous_edit_accepts_only_one_writer(manager):
    site = create(manager)
    current = state(manager, site)
    auth = manager.auth
    registry = SiteRegistry(
        manager.app.state.database,
        authorize_actor=lambda conn, user: auth.authorize_session(conn, manager.token, user),
    )
    barrier = Barrier(2)

    def edit(body):
        barrier.wait(timeout=5)
        try:
            return registry.update_settings(
                site["site_id"], manager.user, **settings_payload(current, welcome_body=body)
            )
        except SiteConflictError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(edit, ["Writer one", "Writer two"]))
    assert sum(result is not None for result in results) == 1
    assert state(manager, site)["settings_revision"] == 2


def test_renew_expired_claim_stale_renewal_and_old_proof(manager, pg_database, monkeypatch):
    site = create(manager)
    path = f"/api/v1/sites/{site['site_id']}"
    with pg_database.begin() as connection:
        connection.execute(
            update(site_claims).values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    monkeypatch.setattr(
        "node06_service.verifier.fetch_in_process", lambda *_: site["proof_document"].encode()
    )
    assert manager.client.post(path + "/verify", json={}).status_code == 409
    payload = {"expected_claim_id": site["claim_id"]}
    renewal = manager.client.post(path + "/claim/renew", json=payload)
    assert renewal.status_code == 200, renewal.text
    assert renewal.json()["claim_id"] != site["claim_id"]
    assert manager.client.post(path + "/claim/renew", json=payload).status_code == 409
    assert manager.client.post(path + "/verify", json={}).json()["code"] == "PROOF_MISMATCH"
    monkeypatch.setattr(
        "node06_service.verifier.fetch_in_process",
        lambda *_: renewal.json()["proof_document"].encode(),
    )
    assert manager.client.post(path + "/verify", json={}).status_code == 200
    assert (
        manager.client.post(
            path + "/claim/renew", json={"expected_claim_id": renewal.json()["claim_id"]}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("mutation", ["logout", "renew"])
def test_management_changes_during_fetch_cannot_activate(
    manager, pg_database, monkeypatch, mutation
):
    site = create(manager)

    def fetch(_origin, _seconds):
        if mutation == "logout":
            manager.auth.logout(manager.token, all_sessions=True)
        else:
            SiteRegistry(pg_database).renew_claim(site["site_id"], manager.user, site["claim_id"])
        return site["proof_document"].encode()

    monkeypatch.setattr("node06_service.verifier.fetch_in_process", fetch)
    response = manager.client.post(f"/api/v1/sites/{site['site_id']}/verify", json={})
    assert response.status_code == (401 if mutation == "logout" else 404), response.text
    with pg_database.connect() as connection:
        assert connection.execute(select(sites.c.state)).scalar_one() == "pending"
        assert connection.execute(select(func.count()).select_from(point_edges)).scalar_one() == 0


def test_attempt_budget_timeout_and_overload_preserve_state(manager, pg_database, monkeypatch):
    site = create(manager)
    path = f"/api/v1/sites/{site['site_id']}"
    manager.app.state.settings.claim_max_attempts = 2
    manager.app.state.settings.verifier_slots = 1
    verifier = ProofVerifier(pg_database, manager.app.state.settings)
    lease = verifier.acquire()
    try:
        busy = manager.client.post(path + "/verify", json={})
        assert busy.status_code == 503 and busy.headers["retry-after"] == "2"
        assert state(manager, site)["attempt_count"] == 0
    finally:
        verifier.release(lease)

    def timeout(*_):
        raise VerifierTimeoutError("deadline")

    monkeypatch.setattr("node06_service.verifier.fetch_in_process", timeout)
    assert manager.client.post(path + "/verify", json={}).status_code == 504
    monkeypatch.setattr("node06_service.verifier.fetch_in_process", lambda *_: b"bad")
    assert manager.client.post(path + "/verify", json={}).status_code == 400
    limited = manager.client.post(path + "/verify", json={})
    assert limited.status_code == 429 and limited.json()["code"] == "SITE_ATTEMPTS_EXCEEDED"
    assert state(manager, site)["attempt_count"] == 2


def test_management_rate_limits(manager, monkeypatch):
    manager.app.state.settings.site_creations_per_hour = 1
    site = create(manager)
    assert (
        manager.client.post(
            "/api/v1/sites", json={"origin": "https://extra.example", "welcome_body": "Hi"}
        ).status_code
        == 429
    )
    manager.app.state.settings.site_renewals_per_hour = 1
    path = f"/api/v1/sites/{site['site_id']}"
    renewal = manager.client.post(
        path + "/claim/renew", json={"expected_claim_id": site["claim_id"]}
    )
    assert renewal.status_code == 200
    assert (
        manager.client.post(
            path + "/claim/renew", json={"expected_claim_id": renewal.json()["claim_id"]}
        ).status_code
        == 429
    )
    manager.app.state.settings.site_verifications_per_minute = 1
    monkeypatch.setattr("node06_service.verifier.fetch_in_process", lambda *_: b"wrong")
    assert manager.client.post(path + "/verify", json={}).status_code == 400
    assert manager.client.post(path + "/verify", json={}).status_code == 429


def test_input_theme_and_body_bounds_are_checked_before_mutation(manager):
    site = create(manager)
    current = state(manager, site)
    path = f"/api/v1/sites/{site['site_id']}"
    for theme in (
        {"bg": "url(https://tracking.example)"},
        {"stylesheet": "evil"},
        {"radius": True},
        {"radius": 17},
        {"font": "custom"},
    ):
        assert (
            manager.client.patch(path, json=settings_payload(current, theme=theme)).status_code
            == 422
        )
    for body in ("", "x" * 8193, "[word](md://hidden)"):
        assert (
            manager.client.patch(
                path, json=settings_payload(current, welcome_body=body)
            ).status_code
            == 422
        )
    assert (
        manager.client.patch(
            path, content=b"x" * 65537, headers={"Content-Type": "application/json"}
        ).status_code
        == 413
    )
    assert manager.client.get("/api/v1/me/sites?after=not-an-id").status_code == 422
    assert manager.client.get("/api/v1/me/sites?limit=101").status_code == 422
    assert state(manager, site) == current


def test_inactive_and_git_owned_welcome_cannot_use_settings_editor(manager, pg_database):
    site = create(manager)
    current = state(manager, site)
    path = f"/api/v1/sites/{site['site_id']}"
    for values in (
        {"state": "inactive", "welcome_source": "ui"},
        {"state": "pending", "welcome_source": "git"},
    ):
        with pg_database.begin() as connection:
            connection.execute(update(sites).values(**values))
        response = manager.client.patch(
            path, json=settings_payload(current, welcome_body="Rejected")
        )
        assert response.status_code == 409
        assert state(manager, site)["welcome_body"] == current["welcome_body"]
