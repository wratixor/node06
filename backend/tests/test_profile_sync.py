"""Real two-registry preference exchange: consent, convergence, retries and no authority."""

import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from node06_service.models import profile_links, profile_preferences, subscriptions, user_trust
from node06_service.profile_preferences import Entry, now_tick, put
from node06_service.profile_sync_worker import work
from node06_service.public_points import PublicPointError
from sqlalchemy import func, select, update
from test_authoring import attach, payload, post
from test_authoring import static_bundle as static_bundle_fixture
from test_profile_links import A, B, approval, establish
from test_profile_links import pair as pair_fixture
from test_profile_links import peer_database as peer_database_fixture

peer_database = peer_database_fixture
pair = pair_fixture
static_bundle = static_bundle_fixture
SCOPES = ["color", "favorites", "subscriptions", "own_points"]


def connect(pair, send=SCOPES, receive=SCOPES):
    a, b = pair
    r = a.client.post(
        "/api/v1/me/profile-links/invite",
        json={
            "origin": B,
            "send": send,
            "receive": receive,
        },
    )
    assert r.status_code == 200, r.text
    inv = {k: v for k, v in r.json().items() if k != "recipient"}
    answer = approval(pair, inv)
    r = a.client.post("/api/v1/me/profile-links/confirm", json=answer)
    assert r.status_code == 200, r.text
    assert r.json()["profile_sync"] is True
    return [n.client.get("/api/v1/me/profile-links").json()["items"][0]["id"] for n in (a, b)]


def sync(a, lid):
    for _ in range(20):
        r = a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={})
        assert r.status_code == 200, r.text
        if r.json()["complete"]:
            return
    pytest.fail("Sync did not finish")


def preferences(node, kind):
    r = node.client.get("/api/v1/me/profile-sync/preferences", params={"kind": kind})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def color(node, value):
    r = node.client.post(
        "/api/v1/me/geometry", json={"coordinates": value}, headers={"Idempotency-Key": uuid4().hex}
    )
    assert r.status_code == 200, r.text


def bookmark(node, origin, pid, active=True):
    r = node.client.post(
        "/api/v1/me/profile-sync/favorite",
        json={
            "origin": origin,
            "point_id": pid,
            "active": active,
        },
    )
    assert r.status_code == 200, r.text


def link_row(node):
    with node.db.connect() as c:
        return c.execute(select(profile_links)).mappings().one()


def test_bidirectional_color_bookmarks_and_deletions_survive_outage(pair):
    a, b = pair
    lid, _ = connect(pair)
    color(a, [101, 202, 303, 404, 505, 606])
    bookmark(a, A, "example")
    sync(a, lid)
    assert b.client.get("/api/v1/me/geometry").json()["coordinates"] == [
        101,
        202,
        303,
        404,
        505,
        606,
    ]
    assert preferences(b, "favorites")[0]["url"].startswith(A + "/?p=example")
    color(b, [7, 8, 9, 10, 11, 12])
    bookmark(b, A, "example", False)
    real = a.app.state.profile_link_transport

    def unavailable(*_args):
        raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)

    a.app.state.profile_link_transport = unavailable
    r = a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={})
    assert r.status_code == 502
    assert link_row(a)["sync_error"]
    a.app.state.profile_link_transport = real
    sync(a, lid)
    assert a.client.get("/api/v1/me/geometry").json()["coordinates"] == [7, 8, 9, 10, 11, 12]
    assert preferences(a, "favorites") == preferences(b, "favorites") == []
    sync(a, lid)  # another sweep must not resurrect a deleted reference
    for n in pair:
        with n.db.connect() as c:
            assert c.scalar(select(func.count()).select_from(user_trust)) == 0
            assert c.scalar(select(func.count()).select_from(subscriptions)) == 0
            tomb = (
                c.execute(
                    select(profile_preferences).where(profile_preferences.c.kind == "favorites")
                )
                .mappings()
                .one()
            )
            assert tomb["deleted"] is True


def test_native_changes_external_subscriptions_posts_no_local_authority(pair, static_bundle):
    a, b = pair
    for n in pair:
        attach(n, static_bundle)
    first = post(a.client, payload(a.client)).json()
    pid = first["id"]
    root = a.client.get("/api/v1/points/skills-ru").json()
    r = a.client.post(
        "/api/v1/points/skills-ru/subscription",
        json={
            "active": True,
            "revision_id": root["revision_id"],
            "content_digest": root["content_digest"],
        },
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert r.status_code == 200, r.text
    r = a.client.post(
        "/api/v1/me/favorites/skills-ru",
        json={"active": True},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert r.status_code == 200, r.text
    lid, _ = connect(pair)
    sync(a, lid)
    assert any(
        x["point_id"] == pid and x["value"]["author_user_id"] == a.uid
        for x in preferences(b, "own_points")
    )
    assert preferences(b, "subscriptions")[0]["origin"] == A
    assert b.client.get("/api/v1/me/favorites").json()["items"] == []
    with b.db.connect() as c:
        assert c.scalar(select(func.count()).select_from(subscriptions)) == 0
        assert c.scalar(select(func.count()).select_from(user_trust)) == 0
    # Imported own-origin favorite can be removed through the normal bookmark button.
    bookmark(b, B, "skills-ru")
    sync(a, lid)
    assert a.client.get("/api/v1/me/favorites").json()["items"][0]["id"] == "skills-ru"
    r = b.client.post(
        "/api/v1/me/favorites/skills-ru",
        json={"active": False},
        headers={"Idempotency-Key": uuid4().hex},
    )
    assert r.status_code == 200, r.text
    assert b.client.get("/api/v1/me/favorites").json()["items"] == []
    sync(a, lid)
    assert not any(x["origin"] == B for x in preferences(a, "favorites"))


def test_scope_pause_revoke_and_control_only_never_grants_data(pair):
    a, b = pair
    lid, blid = connect(pair, ["color"], ["color"])
    settings = f"/api/v1/me/profile-links/{blid}/sync-settings"
    assert (
        b.client.post(
            settings, json={"enabled": True, "send": SCOPES, "receive": SCOPES}
        ).status_code
        == 409
    )
    assert (
        b.client.post(
            settings, json={"enabled": False, "send": ["color"], "receive": ["color"]}
        ).status_code
        == 200
    )
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 502
    b.client.post(settings, json={"enabled": True, "send": [], "receive": []})
    color(a, [2, 3, 4, 5, 6, 7])
    sync(a, lid)
    assert b.client.get("/api/v1/me/geometry").json()["coordinates"] != [2, 3, 4, 5, 6, 7]
    b.client.post(f"/api/v1/me/profile-links/{blid}/revoke", json={})
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 502
    establish(pair)
    old = a.client.get("/api/v1/me/profile-links").json()["items"][0]
    assert (
        a.client.post(
            f"/api/v1/me/profile-links/{old['id']}/sync-settings",
            json={
                "enabled": True,
                "send": ["color"],
                "receive": ["color"],
            },
        ).status_code
        == 409
    )


def test_pagination_lost_response_idempotency_and_worker(pair):
    a, _b = pair
    lid, _ = connect(pair)
    for n in pair:
        with n.db.begin() as c:
            for i in range(37):
                put(c, n.uid, "favorites", n.origin, f"item-{i:02}", {}, False, n.origin)
    real = a.app.state.profile_link_transport
    once = True

    def lost(origin, op, fields):
        nonlocal once
        result = real(origin, op, fields)
        if op == "sync" and once:
            once = False
            raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)
        return result

    a.app.state.profile_link_transport = lost
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 502
    assert link_row(a)["sync_local_cursor"] is None
    a.app.state.profile_link_transport = real
    # Same event replay is safe after the lost acknowledgement; worker uses persisted cursors.
    for _ in range(12):
        with a.db.begin() as c:
            c.execute(
                update(profile_links).values(
                    sync_next_check=datetime.now(UTC) - timedelta(seconds=1)
                )
            )
        work(a.app)
        if (
            link_row(a)["sync_local_cursor"] is None
            and link_row(a)["sync_peer_cursor"] is None
            and link_row(a)["sync_last_success"]
        ):
            break
    for n in pair:
        with n.db.connect() as c:
            assert (
                c.scalar(
                    select(func.count())
                    .select_from(profile_preferences)
                    .where(
                        profile_preferences.c.kind == "favorites",
                        profile_preferences.c.deleted.is_(False),
                    )
                )
                == 74
            )
    assert link_row(a)["sync_error"] is None


def test_private_token_scope_forged_cursor_future_clock_and_changed_generation(pair):
    a, b = pair
    lid, _ = connect(pair)
    row = link_row(a)
    body = {
        "protocol": "node06-profile-sync/1",
        "link_id": row["remote_id"],
        "user_id": a.uid,
        "send": [],
        "receive": [],
        "entries": [],
        "after": None,
    }
    r = b.machine.post(
        "/api/v1/profile-links/sync",
        data={
            "token": row["remote_token"],
            "packet": json.dumps(body),
        },
    )
    assert r.status_code == 401
    assert (
        b.machine.get(
            "/api/v1/me", headers={"Authorization": "Bearer " + row["remote_data_token"]}
        ).status_code
        == 401
    )
    entry = dict(
        kind="color",
        origin="",
        point_id="",
        value=[1] * 6,
        deleted=False,
        clock=str(now_tick() + 10 * 60 * 1000 * 65536),
        writer_origin=A,
        writer_user_id=a.uid,
        event_id=uuid4().hex,
    )
    assert Entry.model_validate(entry)
    r = b.machine.post(
        "/api/v1/profile-links/sync",
        data={
            "token": row["remote_data_token"],
            "packet": json.dumps({**body, "send": ["color"], "entries": [entry]}),
        },
    )
    assert r.status_code == 409, r.text
    real = a.app.state.profile_link_transport

    def forged(origin, op, fields):
        data = real(origin, op, fields)
        if op == "sync":
            data["next_cursor"] = ["favorites", A, "skip"]
        return data

    a.app.state.profile_link_transport = forged
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 502
    assert link_row(a)["sync_error"] == "PROFILE_SYNC_CURSOR"

    def changed(origin, op, fields):
        data = real(origin, op, fields)
        with a.db.begin() as c:
            c.execute(
                update(profile_links)
                .where(profile_links.c.id == lid)
                .values(sync_generation=profile_links.c.sync_generation + 1)
            )
        return data

    a.app.state.profile_link_transport = changed
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 409


def test_data_consent_cannot_downgrade_to_control_preview_or_redemption(pair):
    a, b = pair
    invite = a.client.post(
        "/api/v1/me/profile-links/invite",
        json={
            "origin": B,
            "send": ["color"],
            "receive": [],
        },
    ).json()
    assert (
        a.machine.post(
            "/api/v1/profile-links/metadata",
            data={
                "secret": invite["secret"],
                "client_id": B,
            },
        ).status_code
        == 409
    )
    stripped = {k: invite[k] for k in ("origin", "id", "secret")}
    assert b.client.post("/api/v1/me/profile-links/inspect", json=stripped).status_code == 502
    inv = {k: v for k, v in invite.items() if k != "recipient"}
    meta = b.client.post("/api/v1/me/profile-links/inspect", json=inv).json()
    altered = {**meta, "send": ["favorites"]}
    assert (
        b.client.post(
            "/api/v1/me/profile-links/approve",
            json={
                "invitation": inv,
                "expected": altered,
            },
        ).status_code
        == 409
    )
    answer = approval(pair, inv)
    assert (
        a.client.post(
            "/api/v1/me/profile-links/confirm",
            json={
                **answer,
                "send": [],
            },
        ).status_code
        == 409
    )
    assert (
        b.machine.post(
            "/api/v1/profile-links/token",
            data={
                "grant_type": "authorization_code",
                "client_id": A,
                "redirect_uri": A + "/profile-sync/",
                "code": answer["code"],
                "code_verifier": link_row(a)["verifier"],
            },
        ).status_code
        == 409
    )
    assert a.client.post("/api/v1/me/profile-links/confirm", json=answer).status_code == 200


def test_versions_ties_duplicates_private_fields_and_source_owned_guard(pair):
    a, b = pair
    lid, _ = connect(pair)
    sync(a, lid)
    row = link_row(a)
    packet = dict(
        protocol="node06-profile-sync/1",
        link_id=row["remote_id"],
        user_id=a.uid,
        send=SCOPES,
        receive=[],
        entries=[],
        after=None,
    )

    def receive(entries):
        return b.machine.post(
            "/api/v1/profile-links/sync",
            data={
                "token": row["remote_data_token"],
                "packet": json.dumps({**packet, "entries": entries}),
            },
        )

    e = dict(
        kind="favorites",
        origin=A,
        point_id="kept",
        value={},
        deleted=False,
        clock=str(now_tick()),
        writer_origin=A,
        writer_user_id=a.uid,
        event_id="1" * 32,
    )
    assert receive([e]).status_code == 200
    newer = {**e, "event_id": "2" * 32, "deleted": True}
    assert receive([newer]).status_code == 200
    assert receive([e]).status_code == 200
    assert preferences(b, "favorites") == []
    assert receive([{**newer, "deleted": False}]).status_code == 409
    assert receive([e, e]).status_code == 422
    for field in ("body", "role", "trust", "password"):
        assert receive([{**e, field: "not a preference"}]).status_code == 422
    assert receive([{**e, "kind": "subscriptions", "origin": B}]).status_code == 200
    assert preferences(b, "subscriptions") == []
    # Settings pages and API cannot leak bearer capabilities or accept a peer cookie.
    listing = b.client.get("/api/v1/me/profile-links").text
    assert row["remote_data_token"] not in listing and row["remote_token"] not in listing
    assert (
        b.client.post(
            "/api/v1/profile-links/sync",
            data={
                "token": row["remote_data_token"],
                "packet": json.dumps(packet),
            },
        ).status_code
        == 403
    )


def test_revocation_retry_worker_delivers_without_private_transfer(pair):
    a, b = pair
    lid, _ = connect(pair)
    real = a.app.state.profile_link_transport

    def unavailable(*_args):
        raise PublicPointError("PROFILE_PEER_UNAVAILABLE", 502)

    a.app.state.profile_link_transport = unavailable
    r = a.client.post(f"/api/v1/me/profile-links/{lid}/revoke", json={})
    assert r.json()["peer_notified"] is False
    assert link_row(a)["remote_data_token"] is None
    a.app.state.profile_link_transport = real
    work(a.app)
    assert link_row(a)["revocation_pending"] is False
    assert link_row(b)["status"] == "revoked"


def test_hidden_original_tombstone_and_expired_disabled_data_grants(pair, static_bundle):
    from node06_service.models import point_hides, users

    a, b = pair
    attach(a, static_bundle)
    pid = post(a.client, payload(a.client)).json()["id"]
    lid, blid = connect(pair)
    sync(a, lid)
    assert preferences(b, "own_points")[0]["point_id"] == pid
    with a.db.begin() as c:
        c.execute(
            point_hides.insert().values(
                scope="server",
                point_id=pid,
                active=True,
                hidden_since=datetime.now(UTC),
                updated_by=a.uid,
            )
        )
    sync(a, lid)
    assert preferences(b, "own_points") == []
    with b.db.begin() as c:
        c.execute(
            update(profile_links)
            .where(profile_links.c.id == blid)
            .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
        )
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 502
    assert b.client.get("/api/v1/me/profile-links").json()["profile_sync"] is False
    with b.db.begin() as c:
        c.execute(
            update(profile_links)
            .where(profile_links.c.id == blid)
            .values(expires_at=datetime.now(UTC) + timedelta(days=1))
        )
        c.execute(update(users).where(users.c.id == b.uid).values(state="disabled"))
    assert a.client.post(f"/api/v1/me/profile-links/{lid}/sync", json={}).status_code == 502


def test_populated_migration_roundtrip_preserves_native_settings_and_support(pair, static_bundle):
    import os
    import subprocess
    import sys
    from pathlib import Path

    from node06_service.models import favorite_points, user_geometry, users
    from sqlalchemy import inspect

    a, _b = pair
    attach(a, static_bundle)
    root = a.client.get("/api/v1/points/skills-ru").json()
    for url, body in (
        ("/me/favorites/skills-ru", {"active": True}),
        (
            "/points/skills-ru/subscription",
            {
                "active": True,
                "revision_id": root["revision_id"],
                "content_digest": root["content_digest"],
            },
        ),
    ):
        assert (
            a.client.post(
                "/api/v1" + url, json=body, headers={"Idempotency-Key": uuid4().hex}
            ).status_code
            == 200
        )
    color(a, [3, 4, 5, 6, 7, 8])
    connect(pair)
    with a.db.connect() as c:
        assert c.scalar(select(func.count()).select_from(profile_preferences)) >= 3
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": a.db._engine.url.render_as_string(hide_password=False),
    }
    for command, revision in (("downgrade", "0021_site_author_blocks"), ("upgrade", "head")):
        r = subprocess.run(
            [sys.executable, "-m", "alembic", command, revision],
            cwd=Path(__file__).resolve().parents[2],
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert r.returncode == 0, r.stderr
        assert ("profile_preferences" in inspect(a.db._engine).get_table_names()) == (
            command == "upgrade"
        )
        with a.db.connect() as c:
            assert c.scalar(select(users.c.id).where(users.c.id == a.uid)) == a.uid
            assert c.scalar(
                select(user_geometry.c.coordinates).where(user_geometry.c.user_id == a.uid)
            ) == [3, 4, 5, 6, 7, 8]
            assert (
                c.scalar(
                    select(favorite_points.c.point_id).where(favorite_points.c.user_id == a.uid)
                )
                == "skills-ru"
            )
            assert (
                c.scalar(select(subscriptions.c.active).where(subscriptions.c.user_id == a.uid))
                is True
            )
    # Re-upgrade cannot silently restore a data grant discarded by the downgrade.
    assert link_row(a)["sync_enabled"] is False
    assert link_row(a)["remote_data_token"] is None
