"""Owner-run bootstrap: grant a server role to an exact existing user ID."""

import argparse
import re

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from .config import get_settings
from .db import Database
from .models import moderation_roles, users
from .moderation import log
from .social import lock_graph


def grant(database, user_id, role):
    if not re.fullmatch(r"u_[0-9a-f]{32}", user_id):
        raise ValueError("Expected exact user ID, not a handle")
    if role not in ("admin", "moderator"):
        raise ValueError("Invalid role")
    with database.begin() as c:
        lock_graph(c)
        if not c.scalar(select(users.c.id).where(users.c.id == user_id, users.c.state == "active")):
            raise ValueError("Active user ID not found")
        c.execute(
            insert(moderation_roles)
            .values(scope="server", user_id=user_id, role=role)
            .on_conflict_do_update(
                index_elements=[moderation_roles.c.scope, moderation_roles.c.user_id],
                set_={"role": role},
            )
        )
        log(c, None, "server", "bootstrap", user_id, {"role": role})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", required=True)
    parser.add_argument("--role", choices=("admin", "moderator"), default="admin")
    args = parser.parse_args()
    database = Database(get_settings().database_url)
    try:
        grant(database, args.user_id, args.role)
    finally:
        database.dispose()
    print("Server moderation role granted to the specified existing account.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
