"""First-party point publication. Links declare meaning, never endorsement."""

from uuid import uuid4

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .graph_writes import lock_graph
from .models import (
    authored_points,
    authored_revisions,
    compose_receipts,
    edge_claims,
    events,
    point_edges,
    point_operations,
    point_revisions,
    points,
    sites,
)
from .public_points import PublicPointError
from .root_import import LINK, digest, prose_lines


class AuthoringError(RuntimeError):
    def __init__(self, code, status=422):
        self.code, self.status = code, status


def validate_content(payload):
    body, refs = payload["body"], payload["links"]
    if not body.strip() or len(body.encode()) > 32768:
        raise AuthoringError("INVALID_POINT_BODY")
    ids = [ref["id"] for ref in refs]
    if len(set(ids)) != len(ids):
        raise AuthoringError("DUPLICATE_POINT_LINK")
    for _number, line in prose_lines(body):
        for match in LINK.finditer(line):
            target = match[1]
            if target.startswith("md://") and (
                not target.startswith("md://point/") or target[11:] not in ids
            ):
                raise AuthoringError("UNDECLARED_POINT_LINK")
        if "md://" in LINK.sub("", line):
            raise AuthoringError("UNSUPPORTED_POINT_LINK_SYNTAX")


class Authoring:
    def __init__(self, public, authorize):
        self.public = public
        self.database = public.database
        self.authorize = authorize

    def save(self, actor, key, payload, point_id=None, *, compose_site=None):
        validate_content(payload)
        request_digest = digest({"point_id": point_id, **payload})
        with self.database.begin() as c:
            lock_graph(c)
            # Serializes this actor's receipts and rechecks revocation inside the write.
            self.authorize(c, actor)
            if compose_site is not None:
                active_site = c.scalar(
                    select(sites.c.id).where(
                        sites.c.id == compose_site,
                        sites.c.state == "active",
                        sites.c.primary_origin.is_not(None),
                    )
                )
                if not active_site:
                    raise AuthoringError("SITE_NOT_FOUND", 404)
                # Global key binding prevents replay as a different actor after
                # a popup reload/close or login change. Same actor retries use
                # the existing atomic publication receipt below.
                c.execute(
                    pg_insert(compose_receipts)
                    .values(
                        key=key, user_id=actor, site_id=compose_site, request_digest=request_digest
                    )
                    .on_conflict_do_nothing()
                )
                binding = (
                    c.execute(select(compose_receipts).where(compose_receipts.c.key == key))
                    .mappings()
                    .one()
                )
                if (binding["user_id"], binding["site_id"], binding["request_digest"]) != (
                    actor,
                    compose_site,
                    request_digest,
                ):
                    raise AuthoringError("IDEMPOTENCY_CONFLICT", 409)
            receipt = (
                c.execute(
                    select(point_operations).where(
                        point_operations.c.user_id == actor, point_operations.c.key == key
                    )
                )
                .mappings()
                .one_or_none()
            )
            if receipt:
                if receipt["request_digest"] != request_digest:
                    raise AuthoringError("IDEMPOTENCY_CONFLICT", 409)
                return receipt["response"]
            pid = point_id or "p_" + uuid4().hex
            refs = {ref["id"]: ref for ref in payload["links"]}
            # Core anchors carry no invented revision IDs. All target/current rows are
            # locked together in canonical ID order; no site or target-user locks.
            for target in sorted(refs):
                if target in self.public.core:
                    c.execute(
                        pg_insert(points).values(id=target, origin="root").on_conflict_do_nothing()
                    )
            locked = (
                c.execute(
                    select(points)
                    .where(points.c.id.in_(sorted(set(refs) | {pid})))
                    .order_by(points.c.id)
                    .with_for_update()
                )
                .mappings()
                .all()
            )
            own = next((row for row in locked if row["id"] == pid), None)
            if point_id:
                registered = (
                    c.execute(select(authored_points).where(authored_points.c.point_id == pid))
                    .mappings()
                    .one_or_none()
                )
                if (
                    not own
                    or not registered
                    or own["origin"] != "user"
                    or own["author_user_id"] != actor
                ):
                    raise AuthoringError("POINT_EDIT_FORBIDDEN", 403)
                if own["lifecycle"] != "active":
                    raise AuthoringError("POINT_NOT_ACTIVE", 409)
                if own["current_revision_id"] != payload["expected_revision_id"]:
                    raise AuthoringError("POINT_REVISION_CHANGED", 409)
            if pid in refs:
                raise AuthoringError("SELF_LINK")
            citations = []
            for target, pin in sorted(refs.items()):
                try:
                    current = self.public.raw_on(c, target)
                except PublicPointError:
                    raise AuthoringError("TARGET_NOT_PUBLIC", 409) from None
                if any(current[name] != pin[name] for name in ("revision_id", "content_digest")):
                    raise AuthoringError("TARGET_REVISION_CHANGED", 409)
                citations.append(
                    {
                        "id": target,
                        "revision_id": current["revision_id"],
                        "content_digest": current["content_digest"],
                        "source": current["source"],
                        # Preserve static text across future builds; DB revisions are immutable.
                        "static_body": current.get("body")
                        if current["revision_id"] is None
                        else None,
                    }
                )
            if point_id:
                old = (
                    c.execute(
                        select(
                            point_revisions.c.body,
                            point_revisions.c.declared_links,
                            authored_revisions.c.lang,
                            authored_revisions.c.citations,
                        )
                        .join(
                            authored_revisions,
                            authored_revisions.c.revision_id == point_revisions.c.id,
                        )
                        .where(point_revisions.c.id == own["current_revision_id"])
                    )
                    .mappings()
                    .one()
                )
                if (
                    old["body"] == payload["body"]
                    and old["lang"] == payload["lang"]
                    and old["citations"] == citations
                ):
                    result = {
                        "id": pid,
                        "revision_id": own["current_revision_id"],
                        "changed": False,
                    }
                    self._receipt(c, actor, key, request_digest, result)
                    return result
                from .social_common import active_support

                if c.scalar(select(active_support(pid))):
                    raise AuthoringError("PROPOSAL_REQUIRED", 409)
            else:
                c.execute(insert(points).values(id=pid, origin="user", author_user_id=actor))
                c.execute(insert(authored_points).values(point_id=pid, lang=payload["lang"]))
            revision = "v_" + uuid4().hex
            c.execute(
                insert(point_revisions).values(
                    id=revision,
                    point_id=pid,
                    body=payload["body"],
                    declared_links=sorted(refs),
                    editor_user_id=actor,
                )
            )
            c.execute(
                insert(authored_revisions).values(
                    revision_id=revision, lang=payload["lang"], citations=citations
                )
            )
            c.execute(
                update(points)
                .where(points.c.id == pid)
                .values(
                    current_revision_id=revision,
                    content_updated_at=func.now(),
                    last_interaction_at=func.now(),
                )
            )
            c.execute(
                update(authored_points)
                .where(authored_points.c.point_id == pid)
                .values(lang=payload["lang"])
            )
            c.execute(
                delete(edge_claims).where(
                    edge_claims.c.claim_kind == "authored-point", edge_claims.c.claim_ref == pid
                )
            )
            for target in sorted(refs):
                a, b = sorted((pid, target))
                c.execute(
                    pg_insert(point_edges).values(point_a=a, point_b=b).on_conflict_do_nothing()
                )
                c.execute(
                    insert(edge_claims).values(
                        id="e_" + uuid4().hex,
                        point_a=a,
                        point_b=b,
                        claim_kind="authored-point",
                        claim_ref=pid,
                    )
                )
            c.execute(
                insert(events).values(
                    operation_id="o_" + uuid4().hex,
                    kind="point-edited" if point_id else "point-created",
                    actor_user_id=actor,
                    point_id=pid,
                    payload={
                        "revision_id": revision,
                        "previous_revision_id": own["current_revision_id"] if own else None,
                    },
                )
            )
            result = {"id": pid, "revision_id": revision, "changed": True}
            self._receipt(c, actor, key, request_digest, result)
            return result

    @staticmethod
    def _receipt(c, actor, key, request_digest, result):
        c.execute(
            insert(point_operations).values(
                user_id=actor, key=key, request_digest=request_digest, response=result
            )
        )
