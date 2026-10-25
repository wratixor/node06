"""Explicit scope roles, one report case and reversible hides under the graph lock."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .models import (
    moderation_audit as audit,
)
from .models import (
    moderation_cases as cases,
)
from .models import (
    moderation_reports as reports,
)
from .models import (
    moderation_roles as roles,
)
from .models import (
    point_hides as hides,
)
from .models import (
    point_operations,
    sites,
    users,
)
from .public_points import PublicPointError
from .purge import require_live
from .root_import import digest
from .social import lock_graph
from .visibility import SCOPE


class ModerationError(PublicPointError):
    pass


def scope_on(c, scope):
    if not SCOPE.fullmatch(scope):
        raise ModerationError("INVALID_SCOPE", 422)
    if scope != "server" and not c.scalar(
        select(sites.c.id).where(
            sites.c.id == scope,
            sites.c.state == "active",
            sites.c.primary_origin.is_not(None),
        )
    ):
        raise ModerationError("SCOPE_NOT_FOUND", 404)


def role_on(c, actor, scope):
    server = c.scalar(
        select(roles.c.role).where(roles.c.scope == "server", roles.c.user_id == actor)
    )
    if server == "admin":
        return server
    if scope != "server":
        if c.scalar(select(sites.c.id).where(sites.c.id == scope, sites.c.owner_user_id == actor)):
            return "admin"
        local = c.scalar(
            select(roles.c.role).where(roles.c.scope == scope, roles.c.user_id == actor)
        )
        return local or server
    return server


def require(c, actor, scope, admin=False):
    scope_on(c, scope)
    role = role_on(c, actor, scope)
    if role is None or (admin and role != "admin"):
        raise ModerationError("MODERATION_FORBIDDEN", 403)
    return role


def log(c, actor, scope, action, target, detail):
    c.execute(
        insert(audit).values(
            id="m_" + uuid4().hex,
            actor_id=actor,
            scope=scope,
            action=action,
            target=target,
            detail=detail,
        )
    )


class Moderation:
    def __init__(self, public, authorize):
        self.public, self.database, self.authorize = public, public.database, authorize

    def mutate(self, actor, key, scope, action, target, payload):
        fingerprint = digest(
            {"moderation": action, "scope": scope, "target": target, "payload": payload}
        )
        with self.database.begin() as c:
            lock_graph(c)
            self.authorize(c, actor)
            scope_on(c, scope)
            if action in ("visibility", "report"):
                require_live(c, target)
            if action != "report":
                require(c, actor, scope, admin=action == "role")
            old = (
                c.execute(
                    select(point_operations).where(
                        point_operations.c.user_id == actor,
                        point_operations.c.key == key,
                    )
                )
                .mappings()
                .one_or_none()
            )
            if old:
                if old["request_digest"] != fingerprint:
                    raise ModerationError("IDEMPOTENCY_CONFLICT", 409)
                return old["response"]
            result = getattr(self, "_" + action)(c, actor, scope, target, payload)
            c.execute(
                insert(point_operations).values(
                    user_id=actor, key=key, request_digest=fingerprint, response=result
                )
            )
            return result

    def _report(self, c, actor, scope, target, payload):
        # A site report must refer to a currently public point in that site.
        from .public_points import PublicPoints

        public = PublicPoints(
            self.database,
            roots=self.public.core.values(),
            site_id=None if scope == "server" else scope,
        )
        public.raw_on(c, target)
        c.execute(pg_insert(cases).values(scope=scope, point_id=target).on_conflict_do_nothing())
        added = c.execute(
            pg_insert(reports)
            .values(scope=scope, point_id=target, reporter_id=actor, reason=payload["reason"])
            .on_conflict_do_nothing()
            .returning(reports.c.reporter_id)
        ).scalar_one_or_none()
        if added:
            c.execute(
                update(cases)
                .where(cases.c.scope == scope, cases.c.point_id == target)
                .values(status="open")
            )
            log(c, actor, scope, "report", target, {})
        return {"point_id": target, "scope": scope, "reported": True}

    def _visibility(self, c, actor, scope, target, payload):
        # Moderator review can inspect hidden content, but only after permission check.
        from .public_points import PublicPoints

        active = payload["hidden"]
        previous = (
            c.execute(select(hides).where(hides.c.scope == scope, hides.c.point_id == target))
            .mappings()
            .one_or_none()
        )
        if active or not previous:
            PublicPoints(self.database, roots=self.public.core.values(), moderation=False).raw_on(
                c, target
            )
        since = (
            (previous["hidden_since"] if previous and previous["active"] else datetime.now(UTC))
            if active
            else None
        )
        c.execute(
            pg_insert(hides)
            .values(
                scope=scope, point_id=target, active=active, hidden_since=since, updated_by=actor
            )
            .on_conflict_do_update(
                index_elements=[hides.c.scope, hides.c.point_id],
                set_={
                    "active": active,
                    "hidden_since": since,
                    "updated_by": actor,
                    "updated_at": func.now(),
                },
            )
        )
        log(c, actor, scope, "hide" if active else "restore", target, {"reason": payload["reason"]})
        return {
            "scope": scope,
            "point_id": target,
            "hidden": active,
            "server_hidden_since": since.astimezone(UTC).isoformat()
            if active and scope == "server"
            else None,
        }

    def _close(self, c, actor, scope, target, payload):
        if not c.execute(
            update(cases)
            .where(cases.c.scope == scope, cases.c.point_id == target)
            .values(status="closed")
            .returning(cases.c.point_id)
        ).scalar_one_or_none():
            raise ModerationError("CASE_NOT_FOUND", 404)
        log(c, actor, scope, "close", target, {})
        return {"scope": scope, "point_id": target, "closed": True}

    def _role(self, c, actor, scope, target, payload):
        if target == actor:
            raise ModerationError("SELF_ROLE_CHANGE_FORBIDDEN", 409)
        if not c.scalar(select(users.c.id).where(users.c.id == target, users.c.state == "active")):
            raise ModerationError("USER_NOT_FOUND", 404)
        role = payload["role"]
        if role:
            c.execute(
                pg_insert(roles)
                .values(scope=scope, user_id=target, role=role)
                .on_conflict_do_update(
                    index_elements=[roles.c.scope, roles.c.user_id], set_={"role": role}
                )
            )
        else:
            c.execute(delete(roles).where(roles.c.scope == scope, roles.c.user_id == target))
        log(c, actor, scope, "role", target, {"role": role})
        return {"scope": scope, "user_id": target, "role": role}

    def _ban(self, c, actor, scope, target, payload):
        from .bans import live
        from .models import moderation_bans as bans
        from .models import social_events

        if target == actor:
            raise ModerationError("SELF_BAN_FORBIDDEN", 409)
        if role_on(c, target, scope):
            raise ModerationError("MODERATION_TARGET_PROTECTED", 403)
        if not c.scalar(select(users.c.id).where(users.c.id == target)):
            raise ModerationError("USER_NOT_FOUND", 404)
        previous = (
            c.execute(select(bans).where(bans.c.scope == scope, bans.c.user_id == target, live()))
            .mappings()
            .one_or_none()
        )
        now = c.scalar(select(func.clock_timestamp()))
        start = previous["starts_at"] if previous else now
        mode = payload["mode"]
        end = (
            now + timedelta(seconds=payload["duration_seconds"])
            if mode and payload["duration_seconds"]
            else None
        )
        c.execute(
            pg_insert(bans)
            .values(
                scope=scope,
                user_id=target,
                mode=mode or "block",
                active=mode is not None,
                starts_at=start,
                expires_at=end,
                reason=payload["reason"],
                updated_by=actor,
            )
            .on_conflict_do_update(
                index_elements=[bans.c.scope, bans.c.user_id],
                set_={
                    "mode": mode or "block",
                    "active": mode is not None,
                    "starts_at": start,
                    "expires_at": end,
                    "reason": payload["reason"],
                    "updated_by": actor,
                    "updated_at": now,
                },
            )
        )
        detail = {
            "mode": mode,
            "expires_at": end.isoformat() if end else None,
            "reason": payload["reason"],
        }
        log(c, actor, scope, "ban" if mode else "unban", target, detail)
        # No recipient fanout; invalidate projections without publishing private reasons.
        c.execute(
            insert(social_events).values(
                kind="moderation-ban", actor_user_id=actor, payload={}, public=False, created_at=now
            )
        )
        return {"scope": scope, "user_id": target, **detail}
