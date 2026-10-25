"""Disposable local HTTPS browser acceptance, including the installed wheel.

Run with .venv/bin/python and NODE06_TEST_DATABASE_URL pointing to node06_test_*.
Needs openssl, Node, Playwright (NODE_PATH if bundled) and Chromium. No production use.
"""

import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from uuid import uuid4

from node06_service.auth import AuthService
from node06_service.config import Settings
from node06_service.db import Database
from node06_service.models import point_hides, sites
from node06_service.site_registry import SiteRegistry
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
url = make_url(os.environ["NODE06_TEST_DATABASE_URL"])
if url.drivername != "postgresql+psycopg" or not (url.database or "").startswith("node06_test_"):
    raise SystemExit("Use a dedicated node06_test_* database through psycopg")
schema = "node06_test_" + uuid4().hex
admin = create_engine(url)
servers = []
created = False
temporary = Path(tempfile.mkdtemp(prefix="node06-hosted-browser."))
try:
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    created = True
    isolated = url.update_query_dict({"options": f"-csearch_path={schema}"}).render_as_string(
        hide_password=False
    )
    env = {key: value for key, value in os.environ.items() if not key.startswith("NODE06_")}
    env.update(
        {
            "NODE06_DATABASE_URL": isolated,
            "NODE06_MANAGEMENT_ORIGIN": "https://localhost:8846",
            "NODE06_EMBED_ORIGIN": "https://embed.localhost:8847",
            "NODE06_HOSTED_DIST": str(ROOT / "dist"),
            "NODE06_REGISTRATION_PER_HOUR": "100",
            "NODE06_SITE_CREATIONS_PER_HOUR": "100",
        }
    )

    def run(command, **kwargs):
        return subprocess.run(command, cwd=ROOT, env=env, check=True, **kwargs)

    run([sys.executable, "build.py"])
    # Test the installed wheel against its own immutable build snapshot.
    shutil.copytree(ROOT / "dist", temporary / "dist")
    env["NODE06_HOSTED_DIST"] = str(temporary / "dist")
    env["NODE06_BROWSER_DIST"] = str(temporary / "dist")
    run([sys.executable, "-m", "alembic", "upgrade", "head"], capture_output=True)
    db = Database(isolated)
    owner = (
        AuthService(db, Settings(registration_per_hour=100))
        .register("fixture-owner", "fixture-test-password", "fixture")
        .identity.user_id
    )
    registry = SiteRegistry(db)
    site = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://garden.localhost",
        display_name="Fixture garden",
        welcome_body="<script>window.stolen=1</script>Тест / Test",
    )
    registry.verify_site(
        site.site_id, actor_user_id=owner, proof_fetcher=lambda _: site.proof_document.encode()
    )
    with db.begin() as connection:
        connection.execute(
            update(sites).where(sites.c.id == site.site_id).values(theme={"bg": "#123"})
        )
    other_site = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://other.localhost",
        welcome_body="Other fixture",
    )
    registry.verify_site(
        other_site.site_id,
        actor_user_id=owner,
        proof_fetcher=lambda _: other_site.proof_document.encode(),
    )
    # Pre-existing 30-day hide: exercise actual cleanup before installing the wheel.
    from datetime import timedelta

    from node06_service.graph_writes import lock_graph
    from node06_service.purge import sweep
    from sqlalchemy import func, insert

    purged_site = registry.create_pending_site(
        owner_user_id=owner,
        origin="https://purged.localhost",
        welcome_body="Purged fixture secret",
    )
    registry.verify_site(
        purged_site.site_id,
        actor_user_id=owner,
        proof_fetcher=lambda _: purged_site.proof_document.encode(),
    )
    with db.begin() as connection:
        lock_graph(connection)
        connection.execute(
            insert(point_hides).values(
                scope="server",
                point_id=purged_site.site_id,
                active=True,
                hidden_since=func.clock_timestamp() - timedelta(days=30),
                updated_by=owner,
            )
        )
        assert sweep(connection) == 1
    db.dispose()
    env["NODE06_DEFAULT_SITE_ID"] = site.site_id
    run(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-keyout",
            str(temporary / "key.pem"),
            "-out",
            str(temporary / "cert.pem"),
            "-days",
            "1",
            "-subj",
            "/CN=localhost",
            "-addext",
            "subjectAltName=DNS:localhost,DNS:embed.localhost",
        ],
        capture_output=True,
    )
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "wheel",
            "--no-deps",
            "--wheel-dir",
            str(temporary / "wheels"),
            ".",
        ],
        capture_output=True,
    )
    wheel = next((temporary / "wheels").glob("*.whl"))
    run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-deps",
            "--target",
            str(temporary / "runtime"),
            str(wheel),
        ],
        capture_output=True,
    )
    # Synthetic GitHub data for UI acceptance only; production has no such endpoint.
    # Transport/object/proof failures are tested separately against the actual loader.
    (temporary / "runtime" / "fixture_app.py").write_text(
        """import json
from node06_service.main import create_app
from node06_service.models import git_sources
from node06_service.root_import import GitBlob, RootImportError, prepare_candidate
from sqlalchemy import select
app = create_app()
def fixture_source(repository, branch, site_id, known_commit=None):
    if repository != "fixture/wiki" or branch != "main":
        raise RootImportError("GITHUB_UNAVAILABLE")
    manifest = {"schema_version":1,"site_id":site_id,"content_directory":"site-content",
                "welcome":{"file":"home.md","mode":"git"},
                "points":[{"id":"idea","file":"idea.md","lang":"und"}]}
    candidate = prepare_candidate(json.dumps(manifest).encode(), {
        "site-content/home.md":GitBlob(b"Git fixture home [Idea](md://local/idea)"),
        "site-content/idea.md":GitBlob(b"Git browser point [Home](md://local/welcome)")},
        site_id=site_id, commit_sha="e"*40)
    with app.state.database.connect() as c:
        proof = c.scalar(select(git_sources.c.proof_digest).where(git_sources.c.site_id == site_id))
    return candidate, (123, 456), proof
app.state.source_loader = fixture_source
""",
        encoding="utf-8",
    )
    env["PYTHONPATH"] = str(temporary / "runtime")
    for port in (8846, 8847):
        servers.append(
            subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "fixture_app:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(port),
                    "--ssl-keyfile",
                    str(temporary / "key.pem"),
                    "--ssl-certfile",
                    str(temporary / "cert.pem"),
                    "--no-access-log",
                ],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        )
    # Only this generated, loopback certificate bypasses validation in the fixture.
    tls = ssl._create_unverified_context()
    for port, server in zip((8846, 8847), servers, strict=True):
        deadline = time.monotonic() + 15
        while True:
            if server.poll() is not None:
                raise RuntimeError(
                    "Fixture failed to bind/start; check that ports 8846/8847 are free"
                )
            try:
                with urlopen(
                    f"https://localhost:{port}/api/v1/health", context=tls, timeout=1
                ) as response:
                    if response.status == 200:
                        break
            except OSError:
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("Fixture HTTPS startup timed out")
            time.sleep(0.1)
    env.update(
        {
            "NODE06_TEST_ACTIVE_SITE": site.site_id,
            "NODE06_TEST_OTHER_SITE": other_site.site_id,
            "NODE06_TEST_PURGED_POINT": purged_site.site_id,
            "NODE06_PREVIEW_URL": "https://localhost:8846",
            "NODE06_EMBED_URL": "https://embed.localhost:8847",
        }
    )
    if os.environ.get("NODE06_BROWSER_EXECUTABLE"):
        env["NODE06_BROWSER_EXECUTABLE"] = os.environ["NODE06_BROWSER_EXECUTABLE"]
    check = (
        "scripts/check-home-languages.cjs"
        if os.environ.get("NODE06_HOME_ONLY") == "1"
        else (
            "scripts/check-git-sources.cjs"
            if os.environ.get("NODE06_SOURCE_ONLY") == "1"
            else "scripts/check-hosted-wiki.cjs"
        )
    )
    run(["node", check])
finally:
    for server in servers:
        server.terminate()
    for server in servers:
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait()
    if created:
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    admin.dispose()
    shutil.rmtree(temporary)
