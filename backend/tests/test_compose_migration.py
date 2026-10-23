"""Online old-head upgrade and rollback preserve published points and normal receipts."""

import os
import subprocess
import sys
from pathlib import Path

from node06_service.authoring import Authoring
from node06_service.models import point_operations, point_revisions, points
from node06_service.public_points import PublicPoints
from node06_service.site_registry import SiteRegistry
from sqlalchemy import func, inspect, select

ROOT = Path(__file__).resolve().parents[2]


def test_compose_migration_previous_head_roundtrip(pg_database):
    registry = SiteRegistry(pg_database)
    owner = registry.create_placeholder_user("migration-compose-owner")
    site = registry.create_pending_site(
        owner_user_id=owner, origin="https://migration.example", welcome_body="Root"
    )
    registry.verify_site(
        site.site_id, actor_user_id=owner, proof_fetcher=lambda _: site.proof_document.encode()
    )
    public = PublicPoints(pg_database)
    pin = public.get(site.site_id)
    published = Authoring(public, lambda *_: None).save(
        owner,
        "migration-compose-key",
        {
            "body": "Published before downgrade",
            "lang": "und",
            "links": [{key: pin[key] for key in ("id", "revision_id", "content_digest")}],
        },
        compose_site=site.site_id,
    )
    env = {
        **os.environ,
        "NODE06_DATABASE_URL": pg_database._engine.url.render_as_string(hide_password=False),
    }
    for target in ("0012_social_geometry", "head", "0012_social_geometry", "head"):
        command = "upgrade" if target == "head" else "downgrade"
        result = subprocess.run(
            [sys.executable, "-m", "alembic", command, target],
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, result.stderr
        tables = inspect(pg_database._engine).get_table_names()
        assert ("compose_receipts" in tables) == (target == "head")
        assert "point_operations" in tables and "point_blocks" in tables
        with pg_database.connect() as connection:
            assert (
                connection.scalar(
                    select(points.c.current_revision_id).where(points.c.id == published["id"])
                )
                == published["revision_id"]
            )
            assert (
                connection.scalar(
                    select(point_revisions.c.body).where(
                        point_revisions.c.id == published["revision_id"]
                    )
                )
                == "Published before downgrade"
            )
            assert connection.scalar(select(func.count()).select_from(point_operations)) == 1
