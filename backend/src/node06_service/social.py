"""Version subscriptions, explicit ballots, weighted adoption and durable delivery."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, insert, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert

from .authoring import AuthoringError, validate_content
from .graph_writes import lock_graph
from .influence import InfluenceUnavailable, amount, calculate
from .models import (
    authored_points,
    authored_revisions,
    ballots,
    core_publications,
    edge_claims,
    favorite_points,
    inbox,
    influence_runs,
    point_blocks,
    point_edges,
    point_operations,
    point_revisions,
    points,
    proposals,
    root_entries,
    schema_metadata,
    sites,
    social_events,
    social_user_state,
    subscription_intervals,
    subscriptions,
    support_history,
    user_blocks,
    user_geometry,
    user_trust,
    users,
)
from .public_points import PublicPointError
from .root_import import digest
from .social_common import event, uid


class SocialError(AuthoringError):
    pass


class Social:
    def __init__(self, public, authorize=None, *, clock=None):
        self.public, self.database, self.authorize = public, public.database, authorize
        self.clock = clock or (lambda: datetime.now(UTC))

    def point(self, c, pid):
        if pid in self.public.core:
            c.execute(pg_insert(points).values(id=pid, origin="root").on_conflict_do_nothing())
        return self.public.raw_on(c, pid)

    @staticmethod
    def pin(point):
        return {key: point[key] for key in ("revision_id", "content_digest")}

    def pinned(self, c, pid, payload):
        point = self.point(c, pid)
        if any(point[key] != payload[key] for key in ("revision_id", "content_digest")):
            raise SocialError("POINT_REVISION_CHANGED", 409)
        return point

    def mutate(self, actor, key, kind, target, payload):
        fingerprint = digest({"kind": kind, "target": target, "payload": payload})
        with self.database.begin() as c:
            lock_graph(c)
            self.authorize(c, actor)
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
                    raise SocialError("IDEMPOTENCY_CONFLICT", 409)
                return old["response"]
            result = getattr(self, "_" + kind)(c, actor, target, payload)
            c.execute(
                insert(point_operations).values(
                    user_id=actor, key=key, request_digest=fingerprint, response=result
                )
            )
            return result

    def _favorite(self, c, actor, pid, payload):
        where = (favorite_points.c.user_id == actor) & (favorite_points.c.point_id == pid)
        if not payload["active"]:
            c.execute(delete(favorite_points).where(where))
        else:
            self.point(c, pid)  # Public now; create a real core anchor if needed.
            exists = c.scalar(select(favorite_points.c.point_id).where(where))
            count = c.scalar(
                select(func.count())
                .select_from(favorite_points)
                .where(favorite_points.c.user_id == actor)
            )
            if not exists and count >= 64:
                raise SocialError("FAVORITES_LIMIT", 409)
            c.execute(
                pg_insert(favorite_points)
                .values(user_id=actor, point_id=pid)
                .on_conflict_do_nothing()
            )
        return {"point_id": pid, "active": payload["active"]}

    def _coordinates(self, c, actor, target, payload):
        from .geometry import color, normalized

        values = payload["coordinates"]
        normalized(values)
        old = c.scalar(select(user_geometry.c.coordinates).where(user_geometry.c.user_id == actor))
        if old != values:
            c.execute(
                pg_insert(user_geometry)
                .values(
                    user_id=actor,
                    coordinates=values,
                    updated_at=self.clock(),
                )
                .on_conflict_do_update(
                    index_elements=[user_geometry.c.user_id],
                    set_={"coordinates": values, "updated_at": self.clock()},
                )
            )
            event(c, "coordinates-changed", actor=actor, now=self.clock())
        return {"coordinates": values, "color": color(values)}

    def _remove_block(self, c, actor, pid, reason="explicit-unblock"):
        where = (point_blocks.c.user_id == actor) & (point_blocks.c.point_id == pid)
        old = c.execute(select(point_blocks).where(where)).mappings().one_or_none()
        if old:
            c.execute(delete(point_blocks).where(where))
            seq = event(
                c, "block-changed", pid, actor=actor, payload={"active": False}, now=self.clock()
            )
            c.execute(
                insert(support_history).values(
                    event_seq=seq,
                    user_id=actor,
                    point_id=pid,
                    previous_revision_id=old["revision_id"],
                    previous_digest=old["content_digest"],
                    revision_id=old["revision_id"],
                    content_digest=old["content_digest"],
                    reason=reason,
                )
            )

    def _block(self, c, actor, pid, payload):
        if not payload["active"]:
            self._remove_block(c, actor, pid)
            self._reevaluate(c, pid)
            return {"point_id": pid, "blocked": False}
        point = self.pinned(c, pid, payload)
        pin = self.pin(point)
        if point["revision_id"] is None:
            c.execute(
                pg_insert(core_publications)
                .values(
                    point_id=pid,
                    content_digest=point["content_digest"],
                    body=point["body"],
                    build_revision=point["source"]["build_revision"],
                )
                .on_conflict_do_nothing()
            )
        old = (
            c.execute(
                select(point_blocks).where(
                    point_blocks.c.user_id == actor, point_blocks.c.point_id == pid
                )
            )
            .mappings()
            .one_or_none()
        )
        if old and self.pin(old) == pin:
            return {"point_id": pid, "blocked": True, **pin}
        choices = (
            c.execute(
                select(ballots.c.proposal_id)
                .join(proposals, proposals.c.id == ballots.c.proposal_id)
                .where(
                    ballots.c.user_id == actor,
                    proposals.c.point_id == pid,
                    proposals.c.state == "open",
                )
            )
            .scalars()
            .all()
        )
        for qid in choices:
            c.execute(
                delete(ballots).where(ballots.c.user_id == actor, ballots.c.proposal_id == qid)
            )
            event(
                c,
                "ballot-withdrawn",
                pid,
                actor=actor,
                proposal=qid,
                payload={"reason": "block"},
                now=self.clock(),
            )
        self._set_support(c, actor, pid, pin, active=False, reason="switch-to-block")
        seq = event(
            c, "block-changed", pid, actor=actor, payload={"active": True, **pin}, now=self.clock()
        )
        c.execute(
            pg_insert(point_blocks)
            .values(
                user_id=actor,
                point_id=pid,
                **pin,
                static_body=point.get("body") if point["revision_id"] is None else None,
                updated_at=self.clock(),
            )
            .on_conflict_do_update(
                index_elements=[point_blocks.c.user_id, point_blocks.c.point_id],
                set_={
                    **pin,
                    "static_body": point.get("body") if point["revision_id"] is None else None,
                    "updated_at": self.clock(),
                },
            )
        )
        c.execute(
            insert(support_history).values(
                event_seq=seq,
                user_id=actor,
                point_id=pid,
                previous_revision_id=old["revision_id"] if old else None,
                previous_digest=old["content_digest"] if old else None,
                **pin,
                reason="explicit-block",
            )
        )
        self._reevaluate(c, pid)
        return {"point_id": pid, "blocked": True, **pin}

    def _subscription(self, c, actor, pid, payload):
        point = self.pinned(c, pid, payload)
        q = (
            c.execute(
                select(proposals).where(proposals.c.point_id == pid, proposals.c.state == "open")
            )
            .mappings()
            .one_or_none()
        )
        if q:
            choice = c.scalar(
                select(ballots.c.choice).where(
                    ballots.c.proposal_id == q["id"], ballots.c.user_id == actor
                )
            )
            if payload["active"] and choice == "new":
                raise SocialError("BALLOT_SWITCH_REQUIRED", 409)
            if not payload["active"] and choice:
                c.execute(
                    delete(ballots).where(
                        ballots.c.proposal_id == q["id"], ballots.c.user_id == actor
                    )
                )
                event(
                    c,
                    "ballot-withdrawn",
                    pid,
                    actor=actor,
                    proposal=q["id"],
                    now=self.clock(),
                    payload={"reason": "unsubscribe"},
                )
        self._set_support(
            c,
            actor,
            pid,
            self.pin(point),
            active=payload["active"],
            static_body=point.get("body") if point["revision_id"] is None else None,
        )
        if point["revision_id"] is None:
            c.execute(
                pg_insert(core_publications)
                .values(
                    point_id=pid,
                    content_digest=point["content_digest"],
                    body=point["body"],
                    build_revision=point["source"]["build_revision"],
                )
                .on_conflict_do_nothing()
            )
        self._reevaluate(c, pid)
        return {"point_id": pid, "active": payload["active"], **self.pin(point)}

    def _set_support(
        self, c, actor, pid, pin, *, active=True, static_body=None, reason="explicit-support"
    ):
        if active:
            self._remove_block(c, actor, pid, "switch-to-support")
        old = (
            c.execute(
                select(subscriptions).where(
                    subscriptions.c.user_id == actor, subscriptions.c.point_id == pid
                )
            )
            .mappings()
            .one_or_none()
        )
        if old and old["active"] == active and all(old[k] == pin[k] for k in pin):
            return
        now = self.clock()
        seq = event(
            c, "subscription-changed", pid, actor=actor, payload={"active": active, **pin}, now=now
        )
        values = {**pin, "active": active, "static_body": static_body, "updated_at": now}
        if old:
            c.execute(
                update(subscriptions)
                .where(subscriptions.c.user_id == actor, subscriptions.c.point_id == pid)
                .values(**values)
            )
        else:
            c.execute(insert(subscriptions).values(user_id=actor, point_id=pid, **values))
        if active and (not old or not old["active"]):
            c.execute(
                insert(subscription_intervals).values(
                    id=uid("m"), user_id=actor, point_id=pid, start_seq=seq
                )
            )
        if not active and old and old["active"]:
            c.execute(
                update(subscription_intervals)
                .where(
                    subscription_intervals.c.user_id == actor,
                    subscription_intervals.c.point_id == pid,
                    subscription_intervals.c.end_seq.is_(None),
                )
                .values(end_seq=seq)
            )
        c.execute(
            insert(support_history).values(
                event_seq=seq,
                user_id=actor,
                point_id=pid,
                previous_revision_id=old["revision_id"] if old else None,
                previous_digest=old["content_digest"] if old else None,
                **pin,
                reason=reason,
            )
        )

    def _propose(self, c, actor, pid, payload):
        validate_content(payload)
        current = self.pinned(
            c,
            pid,
            {
                "revision_id": payload["expected_revision_id"],
                "content_digest": payload["expected_digest"],
            },
        )
        if current["source"]["kind"] not in ("user", "site") or pid == "all-sites":
            raise SocialError("POINT_PROTECTED", 403)
        if c.scalar(select(root_entries.c.point_id).where(root_entries.c.point_id == pid)):
            raise SocialError("POINT_PROTECTED", 403)
        if c.scalar(
            select(proposals.c.id).where(proposals.c.point_id == pid, proposals.c.state == "open")
        ):
            raise SocialError("PROPOSAL_ALREADY_OPEN", 409)
        now = self.clock()
        last = c.scalar(
            select(social_user_state.c.last_proposed_at).where(social_user_state.c.user_id == actor)
        )
        if last and now < last + timedelta(hours=24):
            raise SocialError("PROPOSAL_DAILY_LIMIT", 429)
        refs = {ref["id"]: ref for ref in payload["links"]}
        if pid in refs:
            raise SocialError("SELF_LINK")
        citations = []
        for target, pin in sorted(refs.items()):
            value = self.point(c, target)
            if any(value[k] != pin[k] for k in ("revision_id", "content_digest")):
                raise SocialError("TARGET_REVISION_CHANGED", 409)
            citations.append(
                {
                    "id": target,
                    **self.pin(value),
                    "source": value["source"],
                    "static_body": value.get("body") if value["revision_id"] is None else None,
                }
            )
        candidate_digest = digest(
            {"id": pid, "lang": payload["lang"], "body": payload["body"], "links": sorted(refs)}
        )
        if candidate_digest == current["content_digest"]:
            raise SocialError("PROPOSAL_UNCHANGED", 409)
        qid, revision = uid("q"), uid("v")
        c.execute(
            insert(point_revisions).values(
                id=revision,
                point_id=pid,
                body=payload["body"],
                declared_links=sorted(refs),
                editor_user_id=actor,
                created_at=now,
            )
        )
        c.execute(
            insert(proposals).values(
                id=qid,
                point_id=pid,
                author_user_id=actor,
                base_revision_id=current["revision_id"],
                base_digest=current["content_digest"],
                base_body=current["body"],
                base_lang=current["lang"],
                candidate_revision_id=revision,
                candidate_digest=candidate_digest,
                content={
                    "body": payload["body"],
                    "lang": payload["lang"],
                    "links": payload["links"],
                },
                citations=citations,
                created_at=now,
                closes_at=now + timedelta(hours=72),
            )
        )
        c.execute(
            pg_insert(social_user_state)
            .values(user_id=actor, last_proposed_at=now)
            .on_conflict_do_update(
                index_elements=[social_user_state.c.user_id], set_={"last_proposed_at": now}
            )
        )
        event(
            c,
            "proposal-opened",
            pid,
            actor=actor,
            proposal=qid,
            notify=True,
            now=now,
            payload={"base_revision_id": current["revision_id"], "candidate_revision_id": revision},
        )
        return {"proposal_id": qid, "point_id": pid, "state": "open"}

    def _vote(self, c, actor, qid, payload):
        q = self._proposal(c, qid)
        if q["state"] != "open" or self.clock() >= q["closes_at"]:
            raise SocialError("VOTING_CLOSED", 409)
        current = self.point(c, q["point_id"])
        if (
            current["content_digest"] != q["base_digest"]
            or current["revision_id"] != q["base_revision_id"]
        ):
            raise SocialError("PROPOSAL_STALE", 409)
        prior = (
            c.execute(
                select(subscriptions).where(
                    subscriptions.c.user_id == actor, subscriptions.c.point_id == q["point_id"]
                )
            )
            .mappings()
            .one_or_none()
        )
        if not prior or not prior["active"]:
            self._set_support(c, actor, q["point_id"], self.pin(current))
        pin = (
            self.pin(current)
            if payload["choice"] == "old"
            else {
                "revision_id": q["candidate_revision_id"],
                "content_digest": q["candidate_digest"],
            }
        )
        self._set_support(c, actor, q["point_id"], pin, reason="explicit-ballot")
        existing = c.scalar(
            select(ballots.c.choice).where(ballots.c.proposal_id == qid, ballots.c.user_id == actor)
        )
        c.execute(
            pg_insert(ballots)
            .values(
                proposal_id=qid, user_id=actor, choice=payload["choice"], updated_at=self.clock()
            )
            .on_conflict_do_update(
                index_elements=[ballots.c.proposal_id, ballots.c.user_id],
                set_={"choice": payload["choice"], "updated_at": self.clock()},
            )
        )
        if existing != payload["choice"]:
            event(
                c,
                "ballot-cast",
                q["point_id"],
                actor=actor,
                proposal=qid,
                payload={"choice": payload["choice"]},
                now=self.clock(),
            )
        self._finalize(c, q)
        return {
            "proposal_id": qid,
            "choice": payload["choice"],
            "state": self._proposal(c, qid)["state"],
        }

    def _read_notice(self, c, actor, target, payload):
        seq = int(target)
        found = (
            c.execute(select(inbox).where(inbox.c.user_id == actor, inbox.c.event_seq == seq))
            .mappings()
            .one_or_none()
        )
        if not found:
            raise SocialError("NOTICE_NOT_FOUND", 404)
        if found["read_at"] is None:
            c.execute(
                update(inbox)
                .where(inbox.c.user_id == actor, inbox.c.event_seq == seq)
                .values(read_at=self.clock())
            )
        return {"event_seq": seq, "read": True}

    def _person_block(self, c, actor, target, payload):
        if target == actor or not c.scalar(select(users.c.id).where(users.c.id == target)):
            raise SocialError("INVALID_TRUST_TARGET")
        where = (user_blocks.c.source_user_id == actor) & (user_blocks.c.target_user_id == target)
        if payload["active"]:
            # Remove the existing T1 edge atomically; no negative edge is added.
            self._trust(c, actor, target, {"active": False})
            c.execute(
                pg_insert(user_blocks)
                .values(source_user_id=actor, target_user_id=target)
                .on_conflict_do_nothing()
            )
        else:
            c.execute(delete(user_blocks).where(where))
        return {"target_user_id": target, "blocked": payload["active"]}

    def _trust(self, c, actor, target, payload):
        if target == actor or not c.scalar(
            select(users.c.id).where(users.c.id == target, users.c.state == "active")
        ):
            raise SocialError("INVALID_TRUST_TARGET")
        if payload["active"] and c.scalar(
            select(user_blocks.c.target_user_id).where(
                user_blocks.c.source_user_id == actor, user_blocks.c.target_user_id == target
            )
        ):
            raise SocialError("AUTHOR_BLOCKED", 409)
        where = (user_trust.c.source_user_id == actor) & (user_trust.c.target_user_id == target)
        had = c.scalar(select(user_trust.c.target_user_id).where(where)) is not None
        if had != payload["active"]:
            if payload["active"]:
                c.execute(insert(user_trust).values(source_user_id=actor, target_user_id=target))
            else:
                c.execute(delete(user_trust).where(where))
            event(
                c,
                "trust-changed",
                actor=actor,
                payload={"target_user_id": target, "active": payload["active"]},
                now=self.clock(),
            )
        return {"target_user_id": target, "active": payload["active"]}

    def _proposal(self, c, qid):
        q = c.execute(select(proposals).where(proposals.c.id == qid)).mappings().one_or_none()
        if not q:
            raise SocialError("PROPOSAL_NOT_FOUND", 404)
        return q

    def _snapshot(self, c):
        ids = (
            c.execute(
                select(users.c.id)
                .where(users.c.state == "active")
                .order_by(users.c.id)
                .limit(10001)
                .with_for_update()
            )
            .scalars()
            .all()
        )
        trust = [tuple(row) for row in c.execute(select(user_trust).limit(100001))]
        active = []
        current = {}
        rows = (
            c.execute(
                select(subscriptions)
                .join(users, users.c.id == subscriptions.c.user_id)
                .where(subscriptions.c.active.is_(True), users.c.state == "active")
                .limit(100001)
            )
            .mappings()
            .all()
        )
        blocked = (
            c.execute(
                select(point_blocks)
                .join(users, users.c.id == point_blocks.c.user_id)
                .where(users.c.state == "active")
                .limit(100001)
            )
            .mappings()
            .all()
        )
        if len(rows) + len(blocked) > 100000:
            raise InfluenceUnavailable("INFLUENCE_CAPACITY_EXCEEDED")
        for row in [*rows, *blocked]:
            pid = row["point_id"]
            if pid not in current:
                try:
                    current[pid] = self.public.raw_on(c, pid)
                except PublicPointError:
                    current[pid] = None
            if current[pid] is not None:
                active.append((row["user_id"], pid))
        data = calculate(ids, trust, active)
        all_allocations = data["allocations"]
        data["allocations"], data["block_allocations"] = {}, {}
        confirmed_support, confirmed_blocks = {}, {}
        mass = held = negative = 0
        point_mass = {}
        for kind, entries in (("support", rows), ("block", blocked)):
            for row in entries:
                actor, pid = row["user_id"], row["point_id"]
                units = all_allocations.get(actor, {}).get(pid, 0)
                point = current[pid]
                allocations = data["allocations" if kind == "support" else "block_allocations"]
                if point:
                    allocations.setdefault(actor, {})[pid] = units
                    entry = point_mass.setdefault(
                        pid,
                        {
                            **self.pin(point),
                            "current": 0,
                            "held": 0,
                            "subscribed": 0,
                            "blocked": 0,
                            "blocked_held": 0,
                        },
                    )
                    if kind == "support":
                        entry["subscribed"] += units
                confirmed = bool(point and self.pin(point) == self.pin(row))
                if confirmed and kind == "support":
                    mass += units
                    entry["current"] += units
                    confirmed_support.setdefault(actor, {})[pid] = units
                elif confirmed:
                    negative += units
                    entry["blocked"] += units
                    confirmed_blocks.setdefault(actor, {})[pid] = units
                else:
                    held += units
                    if point:
                        entry["held" if kind == "support" else "blocked_held"] += units
        from .geometry import DEFAULT
        from .geometry import calculate as geometry_calculate

        profiles = dict(
            c.execute(
                select(user_geometry.c.user_id, user_geometry.c.coordinates).where(
                    user_geometry.c.user_id.in_(ids)
                )
            ).all()
        )
        profiles = {actor: profiles.get(actor, DEFAULT) for actor in ids}
        geometry = geometry_calculate(profiles, confirmed_support, confirmed_blocks)
        for pid, result in geometry.items():
            result.update(self.pin(current[pid]))
        data.update(
            point_mass=point_mass,
            mass_units=mass,
            blocked_units=negative,
            held_units=held,
            geometry=geometry,
            cutoff_seq=c.scalar(select(func.max(social_events.c.seq))) or 0,
        )
        if mass + negative + held + data["idle_units"] != len(ids) * data["scale"] // 2:
            raise InfluenceUnavailable("MASS_CONSERVATION_FAILED")
        identity = digest(
            {
                "projection": "point-mass/2-geometry/1",
                "profiles": profiles,
                "blocks": [
                    dict(
                        user_id=r["user_id"],
                        point_id=r["point_id"],
                        digest=r["content_digest"],
                        revision=r["revision_id"],
                    )
                    for r in sorted(blocked, key=lambda r: (r["user_id"], r["point_id"]))
                ],
                "cutoff_seq": data["cutoff_seq"],
                "users": ids,
                "trust": sorted(trust),
                "subscriptions": [
                    {
                        "user_id": r["user_id"],
                        "point_id": r["point_id"],
                        "digest": r["content_digest"],
                        "revision": r["revision_id"],
                    }
                    for r in sorted(rows, key=lambda r: (r["user_id"], r["point_id"]))
                ],
                "current": {pid: self.pin(p) if p else None for pid, p in sorted(current.items())},
            }
        )
        previous = (
            c.execute(
                select(influence_runs)
                .order_by(influence_runs.c.created_at.desc(), influence_runs.c.id.desc())
                .limit(1)
            )
            .mappings()
            .one_or_none()
        )
        if previous and previous["input_digest"] == identity:
            return previous["id"], data
        run = uid("i")
        c.execute(
            insert(influence_runs).values(
                id=run, input_digest=identity, data=data, created_at=self.clock()
            )
        )
        return run, data

    def _reevaluate(self, c, pid):
        q = (
            c.execute(
                select(proposals).where(proposals.c.point_id == pid, proposals.c.state == "open")
            )
            .mappings()
            .one_or_none()
        )
        if q:
            self._finalize(c, q)

    def _finalize(self, c, q):
        if q["state"] != "open":
            return
        try:
            current = self.public.raw_on(c, q["point_id"])
        except PublicPointError:
            current = None
        if not current or self.pin(current) != {
            "revision_id": q["base_revision_id"],
            "content_digest": q["base_digest"],
        }:
            self._close(c, q, "stale", {"reason": "base-changed"})
            return
        if current["source"]["kind"] not in ("user", "site"):
            self._close(c, q, "stale", {"reason": "source-protected"})
            return
        run, data = self._snapshot(c)
        choices = dict(
            c.execute(
                select(ballots.c.user_id, ballots.c.choice).where(ballots.c.proposal_id == q["id"])
            ).all()
        )
        total = old = new = 0
        for actor, allocations in data["allocations"].items():
            units = allocations.get(q["point_id"], 0)
            total += units
            if choices.get(actor) == "new":
                new += units
            elif choices.get(actor) == "old":
                old += units
        early = total > 0 and new == total
        due = self.clock() >= q["closes_at"]
        if not early and not due:
            return
        result = {
            "snapshot_id": run,
            "model": data["model"],
            "old_influence": amount(old),
            "new_influence": amount(new),
            "subscribed_influence": amount(total),
            "early": early,
        }
        if new > old and (early or due):
            for pin in q["content"]["links"]:
                try:
                    target = self.public.raw_on(c, pin["id"])
                except PublicPointError:
                    target = None
                if not target or self.pin(target) != {
                    k: pin[k] for k in ("revision_id", "content_digest")
                }:
                    self._close(c, q, "stale", {**result, "reason": "target-changed"})
                    return
            self._adopt(c, q)
            self._close(c, q, "adopted", result)
        else:
            self._close(c, q, "retained", result)

    def _close(self, c, q, state, result):
        c.execute(
            update(proposals).where(proposals.c.id == q["id"]).values(state=state, result=result)
        )
        event(
            c,
            "proposal-" + state,
            q["point_id"],
            proposal=q["id"],
            payload=result,
            notify=True,
            now=self.clock(),
        )

    def _adopt(self, c, q):
        pid = q["point_id"]
        content = q["content"]
        refs = sorted(ref["id"] for ref in content["links"])
        now = self.clock()
        c.execute(
            insert(authored_revisions).values(
                revision_id=q["candidate_revision_id"],
                lang=content["lang"],
                citations=q["citations"],
            )
        )
        c.execute(
            pg_insert(authored_points)
            .values(point_id=pid, lang=content["lang"])
            .on_conflict_do_update(
                index_elements=[authored_points.c.point_id], set_={"lang": content["lang"]}
            )
        )
        c.execute(
            update(points)
            .where(points.c.id == pid)
            .values(
                current_revision_id=q["candidate_revision_id"],
                content_updated_at=now,
                last_interaction_at=now,
            )
        )
        c.execute(
            update(sites)
            .where(sites.c.id == pid)
            .values(settings_revision=sites.c.settings_revision + 1, updated_at=now)
        )
        c.execute(
            delete(edge_claims).where(
                edge_claims.c.claim_kind == "authored-point", edge_claims.c.claim_ref == pid
            )
        )
        for target in refs:
            a, b = sorted((pid, target))
            c.execute(pg_insert(point_edges).values(point_a=a, point_b=b).on_conflict_do_nothing())
            c.execute(
                insert(edge_claims).values(
                    id=uid("e"), point_a=a, point_b=b, claim_kind="authored-point", claim_ref=pid
                )
            )

    def work(self, limit=20):
        with self.database.begin() as c:
            lock_graph(c)
            self._sync_core(c)
            due = (
                c.execute(
                    select(proposals)
                    .where(proposals.c.state == "open", proposals.c.closes_at <= self.clock())
                    .order_by(proposals.c.closes_at, proposals.c.id)
                    .limit(limit)
                )
                .mappings()
                .all()
            )
            for q in due:
                self._finalize(c, q)
            cursor = (
                c.scalar(
                    select(schema_metadata.c.value).where(schema_metadata.c.key == "social-sweep")
                )
                or ""
            )
            query = (
                select(proposals)
                .where(proposals.c.state == "open", proposals.c.id > cursor)
                .order_by(proposals.c.id)
                .limit(limit)
            )
            sweep = c.execute(query).mappings().all()
            if not sweep:
                sweep = (
                    c.execute(
                        select(proposals)
                        .where(proposals.c.state == "open")
                        .order_by(proposals.c.id)
                        .limit(limit)
                    )
                    .mappings()
                    .all()
                )
            for q in sweep:
                self._finalize(c, q)
            if sweep:
                c.execute(
                    pg_insert(schema_metadata)
                    .values(key="social-sweep", value=sweep[-1]["id"])
                    .on_conflict_do_update(
                        index_elements=[schema_metadata.c.key], set_={"value": sweep[-1]["id"]}
                    )
                )
            self._snapshot(c)
            self._deliver(c, limit)

    def _sync_core(self, c):
        for pid, p in self.public.core.items():
            old = (
                c.execute(select(core_publications).where(core_publications.c.point_id == pid))
                .mappings()
                .one_or_none()
            )
            if not old:
                # Baseline every visible core root, including those without subscribers,
                # so later Git changes are still recorded in the public changelog.
                c.execute(pg_insert(points).values(id=pid, origin="root").on_conflict_do_nothing())
                c.execute(
                    insert(core_publications).values(
                        point_id=pid,
                        content_digest=p["content_digest"],
                        body=p["body"],
                        build_revision=p["source"]["build_revision"],
                    )
                )
                continue
            lifecycle = c.scalar(select(points.c.lifecycle).where(points.c.id == pid))
            if old["content_digest"] != p["content_digest"] or lifecycle != "active":
                c.execute(update(points).where(points.c.id == pid).values(lifecycle="active"))
                git_update(
                    c,
                    pid,
                    None,
                    p["content_digest"],
                    p["source"]["build_revision"],
                    static_body=p.get("body"),
                    now=self.clock(),
                )
                c.execute(
                    update(core_publications)
                    .where(core_publications.c.point_id == pid)
                    .values(
                        content_digest=p["content_digest"],
                        body=p["body"],
                        build_revision=p["source"]["build_revision"],
                    )
                )

        removed = (
            c.execute(
                select(core_publications.c.point_id)
                .join(points, points.c.id == core_publications.c.point_id)
                .where(
                    core_publications.c.point_id.not_in(list(self.public.core)),
                    points.c.lifecycle != "retired",
                )
            )
            .scalars()
            .all()
        )
        for pid in removed:
            c.execute(update(points).where(points.c.id == pid).values(lifecycle="retired"))
            event(
                c,
                "git-source-retired",
                pid,
                public=True,
                now=self.clock(),
                payload={"commit": self.public.build_revision},
            )

    def _deliver(self, c, limit):
        for notice in (
            c.execute(
                select(social_events)
                .where(social_events.c.fanout_done.is_(False))
                .order_by(social_events.c.seq)
                .limit(limit)
            )
            .mappings()
            .all()
        ):
            recipients = (
                c.execute(
                    select(subscription_intervals.c.user_id)
                    .where(
                        subscription_intervals.c.point_id == notice["point_id"],
                        subscription_intervals.c.user_id > notice["audience_cursor"],
                        subscription_intervals.c.start_seq <= notice["seq"],
                        or_(
                            subscription_intervals.c.end_seq.is_(None),
                            subscription_intervals.c.end_seq >= notice["seq"],
                        ),
                    )
                    .distinct()
                    .order_by(subscription_intervals.c.user_id)
                    .limit(50)
                )
                .scalars()
                .all()
            )
            for actor in recipients:
                c.execute(
                    pg_insert(inbox)
                    .values(user_id=actor, event_seq=notice["seq"])
                    .on_conflict_do_nothing()
                )
            c.execute(
                update(social_events)
                .where(social_events.c.seq == notice["seq"])
                .values(
                    audience_cursor=recipients[-1] if recipients else notice["audience_cursor"],
                    fanout_done=len(recipients) < 50,
                )
            )


def git_update(c, pid, revision, content_digest, commit, *, static_body=None, now=None):
    """Called in the same locked source-publication transaction, never by a read."""
    seq = event(
        c,
        "git-source-update",
        pid,
        public=True,
        now=now,
        payload={"revision_id": revision, "content_digest": content_digest, "commit": commit},
    )
    c.execute(
        insert(support_history).from_select(
            [
                "event_seq",
                "user_id",
                "point_id",
                "previous_revision_id",
                "previous_digest",
                "revision_id",
                "content_digest",
                "reason",
            ],
            select(
                func.cast(seq, social_events.c.seq.type),
                subscriptions.c.user_id,
                subscriptions.c.point_id,
                subscriptions.c.revision_id,
                subscriptions.c.content_digest,
                func.cast(revision, point_revisions.c.id.type),
                func.cast(content_digest, subscriptions.c.content_digest.type),
                func.cast("git-source-update", support_history.c.reason.type),
            ).where(subscriptions.c.point_id == pid, subscriptions.c.active.is_(True)),
        )
    )
    c.execute(
        update(subscriptions)
        .where(subscriptions.c.point_id == pid, subscriptions.c.active.is_(True))
        .values(
            revision_id=revision,
            content_digest=content_digest,
            static_body=static_body,
            updated_at=now or datetime.now(UTC),
        )
    )

    c.execute(
        insert(support_history).from_select(
            [
                "event_seq",
                "user_id",
                "point_id",
                "previous_revision_id",
                "previous_digest",
                "revision_id",
                "content_digest",
                "reason",
            ],
            select(
                func.cast(seq, social_events.c.seq.type),
                point_blocks.c.user_id,
                point_blocks.c.point_id,
                point_blocks.c.revision_id,
                point_blocks.c.content_digest,
                func.cast(revision, point_revisions.c.id.type),
                func.cast(content_digest, point_blocks.c.content_digest.type),
                func.cast("git-source-update-block", support_history.c.reason.type),
            ).where(point_blocks.c.point_id == pid),
        )
    )
    c.execute(
        update(point_blocks)
        .where(point_blocks.c.point_id == pid)
        .values(
            revision_id=revision,
            content_digest=content_digest,
            static_body=static_body,
            updated_at=now or datetime.now(UTC),
        )
    )
