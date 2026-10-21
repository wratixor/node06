from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from node06_service import auth as auth_module
from node06_service.auth import SESSION_COOKIE, AuthError, AuthService, digest
from node06_service.config import Settings
from node06_service.main import create_app
from node06_service.models import account_credentials, auth_limits, sessions, users
from sqlalchemy import func, select, update

ORIGIN = "https://auth.example"
PASSWORD = "a-long-test-password"


@pytest.fixture
def auth_client(pg_database):
    app = create_app(
        Settings(database_url=None, management_origin=ORIGIN, registration_per_hour=100)
    )
    app.state.database = pg_database
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        yield client


def register(client, handle="alice"):
    response = client.post("/api/v1/auth/register", json={"handle": handle, "password": PASSWORD})
    assert response.status_code == 201, response.text
    return response.json()


def login(client, handle="alice", password=PASSWORD):
    return client.post("/api/v1/auth/login", json={"handle": handle, "password": password})


def test_registration_login_cookie_me_rotation_and_logout(auth_client, pg_database):
    created = register(auth_client)
    assert created["account_created"] is True
    assert created["user_id"].startswith("u_")
    assert len(created["recovery_code"]) == 48
    assert not auth_client.cookies
    assert auth_client.get("/api/v1/me").status_code == 401
    response = login(auth_client)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    for flag in ("HttpOnly", "Secure", "SameSite=strict", "Path=/"):
        assert flag in cookie
    assert "Domain=" not in cookie
    token = auth_client.cookies[SESSION_COOKIE]
    assert token not in response.text and PASSWORD not in response.text
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-security-policy"] == "frame-ancestors 'none'"
    me = auth_client.get("/api/v1/me")
    assert me.json()["user_id"] == created["user_id"]
    assert me.json()["csrf_token"] == response.json()["csrf_token"]
    rotated = login(auth_client)
    assert rotated.status_code == 200
    assert auth_client.cookies[SESSION_COOKIE] != token
    assert AuthService(pg_database, Settings()).authenticate(auth_client.cookies[SESSION_COOKIE])
    with pytest.raises(AuthError):
        AuthService(pg_database, Settings()).authenticate(token)
    assert auth_client.delete("/api/v1/auth/session").status_code == 403
    assert (
        auth_client.delete("/api/v1/auth/session", headers={"X-CSRF-Token": "wrong"}).status_code
        == 403
    )
    assert (
        auth_client.delete(
            "/api/v1/auth/session", headers={"X-CSRF-Token": rotated.json()["csrf_token"]}
        ).status_code
        == 204
    )
    assert auth_client.get("/api/v1/me").status_code == 401


def test_duplicate_registration_is_failure_without_revealing_recovery(auth_client, pg_database):
    created = register(auth_client)
    response = auth_client.post(
        "/api/v1/auth/register", json={"handle": "alice", "password": PASSWORD}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "ACCOUNT_CONFLICT"
    assert "account_created" not in response.json()
    assert created["recovery_code"] not in response.text
    with pg_database.connect() as connection:
        assert connection.execute(select(func.count()).select_from(users)).scalar_one() == 1
        row = connection.execute(select(account_credentials)).mappings().one()
        assert row["password_hash"].startswith("$argon2id$")
        assert PASSWORD not in row["password_hash"]
        assert row["recovery_digest"] == digest(created["recovery_code"])


def test_recovery_rotates_code_password_and_revokes_all_sessions(auth_client, pg_database):
    created = register(auth_client)
    login(auth_client)
    browser_token = auth_client.cookies[SESSION_COOKIE]
    auth = AuthService(pg_database, Settings())
    other_token = auth.login("alice", PASSWORD, "second-browser").token
    recovery = {
        "handle": "alice",
        "password": "a-new-long-password",
        "recovery_code": created["recovery_code"],
    }
    response = auth_client.post("/api/v1/auth/recover", json=recovery)
    assert response.status_code == 200
    replacement = response.json()["recovery_code"]
    assert replacement != created["recovery_code"]
    assert response.json()["password_changed"] is True
    assert auth_client.get("/api/v1/me").status_code == 401
    for token in (browser_token, other_token):
        with pytest.raises(AuthError):
            auth.authenticate(token)
    assert auth_client.post("/api/v1/auth/recover", json=recovery).status_code == 401
    assert login(auth_client).status_code == 401
    assert login(auth_client, password="a-new-long-password").status_code == 200
    assert created["recovery_code"] not in auth_client.get("/api/v1/me").text


def test_unknown_wrong_and_disabled_login_have_same_error(auth_client, pg_database):
    register(auth_client)
    unknown = login(auth_client, "nobody").json()
    wrong = login(auth_client, password="wrong-password-long").json()
    with pg_database.begin() as connection:
        connection.execute(update(users).values(state="disabled"))
    disabled = login(auth_client).json()
    assert unknown["code"] == wrong["code"] == disabled["code"] == "INVALID_CREDENTIALS"


def test_expired_or_disabled_session_is_rejected(pg_database):
    clock = [datetime(2026, 10, 21, tzinfo=UTC)]
    auth = AuthService(pg_database, Settings(), clock=lambda: clock[0])
    created = auth.register("alice", PASSWORD, "test-ip")
    result = auth.login("alice", PASSWORD, "test-ip")
    assert auth.authenticate(result.token) == created.identity
    clock[0] += timedelta(hours=24)
    with pytest.raises(AuthError):
        auth.authenticate(result.token)
    clock[0] -= timedelta(hours=24)
    with pg_database.begin() as connection:
        connection.execute(update(users).values(state="disabled"))
    with pytest.raises(AuthError):
        auth.authenticate(result.token)


def test_recovery_code_is_consumed_once_under_race(pg_database, monkeypatch):
    auth = AuthService(pg_database, Settings())
    created = auth.register("alice", PASSWORD, "test-ip")
    barrier = Barrier(2)
    original = auth_module.hash_password

    def controlled_hash(password):
        result = original(password)
        barrier.wait(timeout=5)
        return result

    monkeypatch.setattr(auth_module, "hash_password", controlled_hash)

    def recover(index):
        try:
            return auth.recover(
                "alice", f"new-password-{index}-long", created.recovery_code, "test-ip"
            )
        except AuthError as exc:
            assert exc.code == "INVALID_RECOVERY"
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(recover, range(2)))
    assert sum(result is not None for result in results) == 1


def test_rate_limits_are_atomic_and_shared_between_service_instances(pg_database):
    barrier = Barrier(4)

    def consume(_index):
        auth = AuthService(pg_database, Settings())
        barrier.wait(timeout=5)
        try:
            auth._limit("test", "same-key", 2, 60)
            return True
        except AuthError as exc:
            assert exc.status == 429 and exc.retry_after == 60
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(consume, range(4))) == 2
    with pg_database.connect() as connection:
        assert connection.execute(select(auth_limits.c.count)).scalar_one() == 2


def test_logout_all_revokes_other_browser_but_not_another_account(auth_client, pg_database):
    register(auth_client)
    register(auth_client, "bob")
    auth = AuthService(pg_database, Settings())
    other_alice = auth.login("alice", PASSWORD, "test-ip").token
    bob = auth.login("bob", PASSWORD, "test-ip").token
    response = login(auth_client)
    assert (
        auth_client.delete(
            "/api/v1/auth/sessions", headers={"X-CSRF-Token": response.json()["csrf_token"]}
        ).status_code
        == 204
    )
    with pytest.raises(AuthError):
        auth.authenticate(other_alice)
    assert auth.authenticate(bob).handle == "bob"


@pytest.mark.parametrize("origin", ["https://evil.example", "null", ""])
def test_cross_origin_registration_cannot_create_an_account(auth_client, pg_database, origin):
    response = auth_client.post(
        "/api/v1/auth/register",
        headers={"Origin": origin},
        json={"handle": "alice", "password": PASSWORD},
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers
    with pg_database.connect() as connection:
        assert connection.execute(select(func.count()).select_from(users)).scalar_one() == 0


def test_secrets_are_not_reflected_by_validation_and_chunked_body_is_bounded():
    app = create_app(Settings(database_url=None, management_origin=ORIGIN))
    with TestClient(app, base_url=ORIGIN, headers={"Origin": ORIGIN}) as client:
        response = client.post(
            "/api/v1/auth/register", json={"handle": "alice", "password": "SECRET"}
        )
        assert response.status_code == 422 and "SECRET" not in response.text
        response = client.post(
            "/api/v1/auth/register",
            content=iter([b"x" * 10000, b"x" * 10000]),
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 413


def test_account_ui_is_unframeable_and_has_no_inline_script():
    with TestClient(create_app(Settings(database_url=None)), base_url=ORIGIN) as client:
        response = client.get("/account/")
        assert response.status_code == 200
        assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert response.headers["cache-control"] == "no-store"
        assert '<script src="/account/client.js" defer>' in response.text
        assert client.get("/account/client.js").status_code == 200
        assert client.get("/account/style.css").status_code == 200


def test_registration_rate_limit_returns_retry_after(pg_database):
    auth = AuthService(pg_database, Settings(registration_per_hour=1))
    auth.register("alice", PASSWORD, "same-ip")
    with pytest.raises(AuthError) as captured:
        auth.register("other", PASSWORD, "same-ip")
    assert captured.value.status == 429 and captured.value.retry_after == 3600


def test_limiter_resets_and_session_database_contains_only_digests(pg_database):
    clock = [datetime(2026, 10, 21, tzinfo=UTC)]
    auth = AuthService(pg_database, Settings(registration_per_hour=1), clock=lambda: clock[0])
    first = auth.register("alice", PASSWORD, "same-ip")
    with pytest.raises(AuthError):
        auth.register("bravo", PASSWORD, "same-ip")
    clock[0] += timedelta(hours=1)
    auth.register("bravo", PASSWORD, "same-ip")
    session = auth.login("alice", PASSWORD, "same-ip")
    with pg_database.connect() as connection:
        stored = connection.execute(select(sessions.c.digest)).scalar_one()
        assert stored == digest(session.token) and session.token not in stored
        assert first.recovery_code not in str(connection.execute(select(account_credentials)).all())


def test_auth_rejects_plain_http_even_with_forged_origin(pg_database):
    app = create_app(Settings(database_url=None, management_origin=ORIGIN))
    app.state.database = pg_database
    with TestClient(app, base_url="http://auth.example", headers={"Origin": ORIGIN}) as client:
        response = client.post(
            "/api/v1/auth/register", json={"handle": "alice", "password": PASSWORD}
        )
        assert response.status_code == 403
        assert response.json()["code"] == "HTTPS_REQUIRED"
