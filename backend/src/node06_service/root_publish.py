"""Privileged operator content release; deliberately not an HTTP import endpoint."""

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError

from .config import get_settings
from .db import Database
from .graph_writes import lock_graph
from .models import (
    edge_claims,
    events,
    point_edges,
    point_revisions,
    points,
    root_entries,
    root_sources,
    sites,
    users,
)
from .purge import purged_ids
from .root_import import RootCandidate, RootImportError
from .root_preflight import GitSnapshot, preflight
from .site_claims import normalize_origin


def publish(
    database: Database,
    candidate: RootCandidate,
    repository_url: str,
    origin: str,
    *,
    check: bool = False,
) -> dict:
    """Atomic operator acceptance, bound to the verified site and original owner.

    The OS operator selects the repository, not a manifest or web caller. No
    registration or source-proof claim is fabricated. All IO precedes this call.
    External references are deferred until trusted revision-pin indexing exists.
    """
    with database.begin() as connection:
        return publish_on(connection, candidate, repository_url, origin, check=check)


def publish_on(connection, candidate, repository_url, origin, *, check=False, authority="operator"):
    """Trusted callers must authorize/validate a source before sharing this transaction."""
    if normalize_origin(origin) != origin:
        raise RootImportError("NON_CANONICAL_ORIGIN")
    if any(p.external_revision_pins for p in candidate.points):
        raise RootImportError("EXTERNAL_PINS_NOT_YET_SUPPORTED")
    welcome = next((p for p in candidate.points if p.id == candidate.site_id), None)
    if welcome is None:
        raise RootImportError("OPERATOR_WELCOME_REQUIRED")
    now = datetime.now(UTC)
    lock_graph(connection)
    site = (
        connection.execute(select(sites).where(sites.c.id == candidate.site_id).with_for_update())
        .mappings()
        .one_or_none()
    )
    if not site or site["state"] != "active" or site["primary_origin"] != origin:
        raise RootImportError("ACTIVE_SITE_ORIGIN_REQUIRED")
    owner = connection.execute(
        select(users.c.state).where(users.c.id == site["owner_user_id"]).with_for_update()
    ).scalar_one()
    if owner != "active":
        raise RootImportError("OWNER_DISABLED")
    source = (
        connection.execute(select(root_sources).where(root_sources.c.site_id == candidate.site_id))
        .mappings()
        .one_or_none()
    )
    if source and (
        source["owner_user_id"] != site["owner_user_id"]
        or source["origin"] != origin
        or source["repository_url"] != repository_url
    ):
        raise RootImportError("SOURCE_BINDING_CHANGED")
    if not source and site["welcome_source"] != "ui":
        raise RootImportError("WELCOME_ALREADY_GIT_MANAGED")
    if source and site["welcome_source"] != "git":
        raise RootImportError("WELCOME_OWNERSHIP_CHANGED")
    existing = {
        r["point_id"]: r
        for r in connection.execute(
            select(root_entries).where(root_entries.c.site_id == candidate.site_id)
        ).mappings()
    }
    incoming = {p.id: p for p in candidate.points}
    if purged_ids(connection, incoming):
        raise RootImportError("POINT_PURGED")
    touched = set(existing) | set(incoming)
    current = {
        r["id"]: r
        for r in connection.execute(
            select(points)
            .where(points.c.id.in_(sorted(touched)))
            .order_by(points.c.id)
            .with_for_update()
        ).mappings()
    }
    for pid, row in existing.items():
        if current[pid]["current_revision_id"] != row["revision_id"]:
            raise RootImportError("ROOT_REVISION_CONFLICT")
    for pid in incoming.keys() - existing.keys():
        if pid in current and pid != candidate.site_id:
            raise RootImportError("ROOT_ID_COLLISION")
    changed = [
        p
        for p in candidate.points
        if p.id not in existing
        or p.content_digest != existing[p.id]["content_digest"]
        or current[p.id]["lifecycle"] != "active"
    ]
    retired = [
        pid for pid in existing.keys() - incoming.keys() if current[pid]["lifecycle"] != "retired"
    ]
    git_home = candidate.home_page.model_dump() if candidate.home_page is not None else None
    home_changed = site["git_home_page"] != git_home
    summary = {
        "site_id": candidate.site_id,
        "commit_sha": candidate.commit_sha,
        "candidate_digest": candidate.digest,
        "changed": len(changed),
        "retired": len(retired),
        "home_changed": home_changed,
        "check_only": check,
        "source_authority": authority,
        "writes_performed": False,
    }
    if check or (
        source
        and source["candidate_digest"] == candidate.digest
        and not changed
        and not retired
        and not home_changed
    ):
        return summary
    source_values = dict(
        owner_user_id=site["owner_user_id"],
        origin=origin,
        repository_url=repository_url,
        commit_sha=candidate.commit_sha,
        candidate_digest=candidate.digest,
        updated_at=now,
    )
    if source:
        connection.execute(
            update(root_sources)
            .where(root_sources.c.site_id == candidate.site_id)
            .values(**source_values)
        )
    else:
        connection.execute(insert(root_sources).values(site_id=candidate.site_id, **source_values))
    for point in changed:
        if point.id not in current:
            connection.execute(insert(points).values(id=point.id, origin="root"))
        revision = "v_" + uuid4().hex
        connection.execute(
            insert(point_revisions).values(
                id=revision,
                point_id=point.id,
                body=point.body,
                declared_links=list(point.links),
            )
        )
        connection.execute(
            update(points)
            .where(points.c.id == point.id)
            .values(
                current_revision_id=revision,
                lifecycle="active",
                content_updated_at=now,
                last_interaction_at=now,
            )
        )
        entry = dict(revision_id=revision, lang=point.lang, content_digest=point.content_digest)
        if point.id in existing:
            connection.execute(
                update(root_entries).where(root_entries.c.point_id == point.id).values(**entry)
            )
        else:
            connection.execute(
                insert(root_entries).values(point_id=point.id, site_id=candidate.site_id, **entry)
            )
        from .social import git_update

        git_update(
            connection, point.id, revision, point.content_digest, candidate.commit_sha, now=now
        )
    for pid in retired:
        connection.execute(
            update(points)
            .where(points.c.id == pid)
            .values(lifecycle="retired", content_updated_at=now)
        )
        from .social_common import event

        event(
            connection,
            "git-source-retired",
            pid,
            public=True,
            now=now,
            payload={"commit": candidate.commit_sha},
        )
    # Release only this source's claims. Other claims/points/revisions survive.
    connection.execute(
        delete(edge_claims).where(
            edge_claims.c.claim_kind == "operator-git-root",
            edge_claims.c.claim_ref == candidate.site_id,
        )
    )
    pairs = {tuple(sorted((p.id, target))) for p in candidate.points for target in p.links}
    for a, b in sorted(pairs):
        connection.execute(
            pg_insert(point_edges).values(point_a=a, point_b=b).on_conflict_do_nothing()
        )
        connection.execute(
            insert(edge_claims).values(
                id="e_" + uuid4().hex,
                point_a=a,
                point_b=b,
                claim_kind="operator-git-root",
                claim_ref=candidate.site_id,
            )
        )
    if site["welcome_source"] != "git" or changed or retired or home_changed:
        connection.execute(
            update(sites)
            .where(sites.c.id == candidate.site_id)
            .values(
                welcome_source="git",
                git_home_page=git_home,
                settings_revision=site["settings_revision"] + 1,
                updated_at=now,
            )
        )
    connection.execute(
        insert(events).values(
            operation_id="o_" + uuid4().hex,
            kind="operator_roots_published" if authority == "operator" else "owner_roots_published",
            actor_user_id=site["owner_user_id"] if authority == "owner" else None,
            site_id=candidate.site_id,
            point_id=candidate.site_id,
            payload={**summary, "repository_url": repository_url, "writes_performed": True},
        )
    )
    return {**summary, "writes_performed": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--site-id", required=True)
    parser.add_argument("--origin", required=True)
    parser.add_argument("--repository-url", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    database = Database(get_settings().database_url)
    try:
        snapshot = GitSnapshot(args.repo, args.commit)
        if snapshot.git("remote", "get-url", "origin").decode().strip() != args.repository_url:
            raise RootImportError("REPOSITORY_ORIGIN_MISMATCH")
        head = snapshot.git("rev-parse", "refs/remotes/origin/main").decode().strip()
        if head != args.commit:
            raise RootImportError("REGISTERED_MAIN_SHA_REQUIRED")
        candidate = preflight(args.repo, args.commit, args.site_id, "node06-roots.json")
        result = publish(database, candidate, args.repository_url, args.origin, check=args.check)
    except RootImportError as exc:
        print(json.dumps({"code": exc.code, "file": exc.path, "writes_performed": False}))
        return 1
    except (SQLAlchemyError, OSError, ValueError):
        print(json.dumps({"code": "ROOT_PUBLICATION_FAILED", "writes_performed": False}))
        return 1
    finally:
        database.dispose()
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
