"""Serialize graph/source/social mutations before taking any user/point locks."""

from sqlalchemy import text


def lock_graph(connection):
    if connection.dialect.name == "postgresql":
        connection.execute(text("SELECT pg_advisory_xact_lock(16006, 1)"))
