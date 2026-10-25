"""Personal site filters never transfer or change server-wide trust/point reactions."""

from uuid import uuid4

from node06_service.models import point_blocks, site_user_blocks, sites, user_blocks, user_trust
from sqlalchemy import func, select, update
from test_authoring import payload, post
from test_people import action
from test_site_management import create
from test_social import manager as manager
from test_social import second, setup
from test_social import static_bundle as static_bundle


def site_action(client, uid, site, active=True, key=None):
    return client.post(
        f"/api/v1/people/{uid}/site-block",
        params={"site": site},
        json={"active": active},
        headers={"Idempotency-Key": key or uuid4().hex},
    )


def test_site_filter_independent_from_other_sites_server_trust_and_profile_export(
    manager, static_bundle, pg_database
):
    setup(manager, static_bundle)
    a = create(manager, "https://one.example")["site_id"]
    b = create(manager, "https://two.example")["site_id"]
    with pg_database.begin() as c:
        c.execute(update(sites).values(state="active", primary_origin=sites.c.claimed_origin))
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    pid = post(bob, payload(bob, body="Site author filter fixture")).json()["id"]
    alice = manager.client
    assert action(alice, uid, "trust").status_code == 200

    def feed(site):
        return [
            p["id"] for p in alice.get("/api/v1/me/feed", params={"site": site}).json()["items"]
        ]

    assert pid in feed(a) and pid in feed(b)
    key = uuid4().hex
    assert site_action(alice, uid, a, key=key).status_code == 200
    assert site_action(alice, uid, a, key=key).status_code == 200
    assert site_action(alice, uid, b, key=key).status_code == 409
    assert pid not in feed(a) and pid in feed(b)
    assert alice.get(f"/api/v1/me/people/{uid}").json()["following"] is True
    assert (
        alice.get(f"/api/v1/me/people/{uid}/site-block", params={"site": a}).json()["blocked"]
        is True
    )
    assert (
        alice.get(f"/api/v1/me/people/{uid}/site-block", params={"site": b}).json()["blocked"]
        is False
    )
    rows = alice.get("/api/v1/me/site-people-blocks").json()["items"]
    assert rows == [{"site_id": a, "id": uid, "handle": "bobby"}]
    export = alice.get("/api/v1/me/profile-export")
    assert export.status_code == 200
    assert "blocks" not in export.text
    with pg_database.connect() as c:
        assert c.scalar(select(func.count()).select_from(user_trust)) == 1
        assert c.scalar(select(func.count()).select_from(user_blocks)) == 0
        assert c.scalar(select(func.count()).select_from(point_blocks)) == 0
        assert c.scalar(select(func.count()).select_from(site_user_blocks)) == 1
    assert site_action(alice, uid, b).status_code == 200
    assert site_action(alice, uid, a, False).status_code == 200
    assert pid in feed(a) and pid not in feed(b)
    # Server block remains independent and suppresses both site feeds, removing trust.
    assert action(alice, uid, "block").status_code == 200
    assert pid not in feed(a) and pid not in feed(b)
    assert action(alice, uid, "block", False).status_code == 200
    assert alice.get(f"/api/v1/me/people/{uid}").json()["following"] is False
    assert (
        alice.get(f"/api/v1/me/people/{uid}/site-block", params={"site": b}).json()["blocked"]
        is True
    )


def test_site_filter_scope_and_csrf_guards(manager, static_bundle, pg_database):
    setup(manager, static_bundle)
    bob = second(manager)
    uid = bob.get("/api/v1/me").json()["user_id"]
    site = create(manager)["site_id"]
    with pg_database.begin() as c:
        c.execute(
            update(sites)
            .where(sites.c.id == site)
            .values(state="active", primary_origin=sites.c.claimed_origin)
        )
    assert (
        manager.client.post(
            f"/api/v1/people/{uid}/site-block",
            json={"active": True},
            headers={"Idempotency-Key": uuid4().hex},
        ).status_code
        == 422
    )
    assert site_action(manager.client, uid, "s_" + "f" * 32).status_code == 404
    assert site_action(manager.client, manager.user, site).status_code == 422
    response = manager.client.post(
        f"/api/v1/people/{uid}/site-block?site=" + site,
        json={"active": True},
        headers={"Idempotency-Key": uuid4().hex, "X-CSRF-Token": "bad"},
    )
    assert response.status_code == 403
    assert manager.client.get("/api/v1/me/site-people-blocks?after_site=server").status_code == 400
