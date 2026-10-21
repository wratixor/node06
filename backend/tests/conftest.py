"""Disposable PostgreSQL schemas using the same migration/dialect as the service."""

import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from node06_service.db import Database
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def pg_database():
    configured_url = os.environ.get("NODE06_TEST_DATABASE_URL")
    if not configured_url:
        pytest.skip("Set NODE06_TEST_DATABASE_URL to a disposable node06_test_* PostgreSQL DB")
    url = make_url(configured_url)
    if url.drivername != "postgresql+psycopg" or not (url.database or "").startswith(
        "node06_test_"
    ):
        pytest.fail("PostgreSQL tests require psycopg and a dedicated node06_test_* database")
    schema = f"node06_test_{uuid4().hex}"
    admin = create_engine(url)
    with admin.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    isolated_url = url.update_query_dict({"options": f"-csearch_path={schema}"})
    database = Database(isolated_url.render_as_string(hide_password=False))
    env = {**os.environ, "NODE06_DATABASE_URL": isolated_url.render_as_string(hide_password=False)}
    try:
        for revision in ("0001_bootstrap_schema", "0002_site_registry", "head"):
            result = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", revision],
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert result.returncode == 0, result.stderr
        yield database
    finally:
        database.dispose()
        with admin.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()
