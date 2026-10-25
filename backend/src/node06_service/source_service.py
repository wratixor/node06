"""Owner-bound public Git source preview/accept. Network IO never holds graph locks."""

import hashlib
import secrets
from dataclasses import asdict
from datetime import timedelta
from uuid import uuid4

from sqlalchemy import func, insert, or_, select, update

from .github_source import coordinates, fetch
from .graph_writes import lock_graph
from .models import events, point_revisions, points, root_entries, root_sources, sites, users
from .models import git_sources as sources
from .public_points import PublicPointError
from .purge import require_live
from .root_import import CandidatePoint, RootCandidate, RootImportError
from .root_publish import publish_on
from .site_claims import SiteClaimError


class SourceError(PublicPointError):
    def __init__(self, code, status=409):
        super().__init__(code, status)


def restore_candidate(value):
    return RootCandidate(
        **{
            **value,
            "points": tuple(
                CandidatePoint(
                    **{
                        **p,
                        "links": tuple(p["links"]),
                        "external_revision_pins": tuple(
                            tuple(pin) for pin in p["external_revision_pins"]
                        ),
                    }
                )
                for p in value["points"]
            ),
            "warnings": tuple(value["warnings"]),
        }
    )


class Sources:
    def __init__(self, database, *, authorize=None, loader=fetch, verifier=None):
        self.database, self.authorize, self.loader, self.verifier = (
            database,
            authorize,
            loader,
            verifier,
        )

    def owner(self, c, site_id, actor):
        if self.authorize:
            self.authorize(c, actor)
        row = c.execute(select(sites).where(sites.c.id == site_id)).mappings().one_or_none()
        if not row or row["owner_user_id"] != actor:
            raise SourceError("SITE_FORBIDDEN", 403)
        if (
            row["state"] != "active"
            or not row["primary_origin"]
            or c.scalar(select(users.c.state).where(users.c.id == actor)) != "active"
        ):
            raise SourceError("ACTIVE_SITE_REQUIRED", 403)
        require_live(c, site_id)
        return row

    @staticmethod
    def row(c, site_id):
        return (
            c.execute(select(sources).where(sources.c.site_id == site_id)).mappings().one_or_none()
        )

    @staticmethod
    def base(c, site):
        source = c.scalar(
            select(root_sources.c.candidate_digest).where(root_sources.c.site_id == site["id"])
        )
        revisions = c.execute(
            select(points.c.id, points.c.current_revision_id, points.c.lifecycle)
            .join(root_entries, root_entries.c.point_id == points.c.id)
            .where(root_entries.c.site_id == site["id"])
            .order_by(points.c.id)
        ).all()
        return {
            "settings": site["settings_revision"],
            "source": source,
            "revisions": [list(r) for r in revisions],
        }

    def status(self, actor, site_id):
        with self.database.connect() as c:
            site = self.owner(c, site_id, actor)
            row = self.row(c, site_id)
            if not row:
                operator = c.scalar(
                    select(root_sources.c.site_id).where(root_sources.c.site_id == site_id)
                )
                return {"configured": False, "operator_managed": bool(operator)}
            if row["owner_user_id"] != actor or row["origin"] != site["primary_origin"]:
                raise SourceError("SOURCE_BINDING_CHANGED", 403)
            preview = None
            if row["candidate"] and row["preview_expires_at"] > c.scalar(
                select(func.clock_timestamp())
            ):
                candidate = restore_candidate(row["candidate"])
                preview = candidate.summary()
                before = dict(
                    c.execute(
                        select(points.c.id, point_revisions.c.body)
                        .join(point_revisions, point_revisions.c.id == points.c.current_revision_id)
                        .outerjoin(root_entries, root_entries.c.point_id == points.c.id)
                        .where(
                            or_(root_entries.c.site_id == site_id, points.c.id == site_id),
                            points.c.lifecycle == "active",
                        )
                    ).all()
                )
                preview.update(
                    id=row["preview_id"],
                    expires_at=row["preview_expires_at"].isoformat(),
                    comparison=[
                        {"id": p.id, "before": before.get(p.id, ""), "after": p.body}
                        for p in candidate.points
                    ],
                    retired=sorted(set(before) - {p.id for p in candidate.points}),
                    home_before=site["git_home_page"],
                    home_after=candidate.home_page.model_dump() if candidate.home_page else None,
                )
            return {
                "configured": True,
                "operator_managed": False,
                "generation": row["generation"],
                "repository": row["repository"],
                "branch": row["branch"],
                "policy": row["policy"],
                "verified": row["repository_id"] is not None,
                "proof_expires_at": row["proof_expires_at"].isoformat(),
                "last_error": row["last_error"],
                "preview": preview,
                "accepted_preview_id": row["accepted_preview_id"],
            }

    def configure(self, actor, site_id, repository, branch, policy, expected_generation):
        repository, branch = coordinates(repository, branch)
        if policy not in ("manual", "auto"):
            raise SourceError("INVALID_UPDATE_POLICY", 422)
        with self.database.begin() as c:
            lock_graph(c)
            site = self.owner(c, site_id, actor)
            from .bans import publication

            publication(c, actor, site_id, proposal=True)
            old = self.row(c, site_id)
            if (old["generation"] if old else None) != expected_generation:
                raise SourceError("SOURCE_CHANGED")
            published = (
                c.execute(select(root_sources).where(root_sources.c.site_id == site_id))
                .mappings()
                .one_or_none()
            )
            if published and not old:
                raise SourceError("SOURCE_OPERATOR_MANAGED")
            url = "https://github.com/" + repository + ".git"
            if published and published["repository_url"].lower() != url:
                raise SourceError("SOURCE_BINDING_CHANGED")
            now, nonce = c.scalar(select(func.clock_timestamp())), secrets.token_hex(32)
            generation = uuid4().hex
            values = dict(
                owner_user_id=actor,
                origin=site["primary_origin"],
                generation=generation,
                repository=repository,
                branch=branch,
                policy=policy,
                proof_digest=hashlib.sha256(nonce.encode()).hexdigest(),
                proof_expires_at=now + timedelta(hours=1),
                repository_id=None,
                repository_owner_id=None,
                candidate=None,
                preview_id=None,
                preview_base=None,
                preview_expires_at=None,
                accepted_preview_id=None,
                receipt=None,
                last_error=None,
                last_attempt_at=None,
                next_check_at=now,
            )
            if old:
                c.execute(update(sources).where(sources.c.site_id == site_id).values(**values))
            else:
                c.execute(insert(sources).values(site_id=site_id, **values))
            c.execute(
                insert(events).values(
                    operation_id="o_" + uuid4().hex,
                    kind="git_source_configured",
                    actor_user_id=actor,
                    site_id=site_id,
                    point_id=site_id,
                    payload={"repository": repository, "branch": branch, "policy": policy},
                )
            )
            return {
                "generation": generation,
                "source_proof": nonce,
                "proof_expires_at": values["proof_expires_at"].isoformat(),
            }

    def checked(self, c, actor, site_id, generation):
        site = self.owner(c, site_id, actor)
        row = self.row(c, site_id)
        if not row or row["generation"] != generation:
            raise SourceError("SOURCE_CHANGED")
        if row["owner_user_id"] != actor or row["origin"] != site["primary_origin"]:
            raise SourceError("SOURCE_BINDING_CHANGED")
        return site, row

    def refresh(self, actor, site_id, generation, *, automatic=False):
        with self.database.begin() as c:
            lock_graph(c)
            site, row = self.checked(c, actor, site_id, generation)
            from .bans import publication

            publication(c, actor, site_id, proposal=True)
            now = c.scalar(select(func.clock_timestamp()))
            if automatic and (
                row["policy"] != "auto"
                or row["repository_id"] is None
                or row["receipt"] is None
                or row["next_check_at"] > now
            ):
                return None
            if row["last_attempt_at"] and row["last_attempt_at"] > now - timedelta(minutes=1):
                raise SourceError("SOURCE_RATE_LIMITED", 429)
            base = self.base(c, site)
            c.execute(
                update(sources)
                .where(sources.c.site_id == site_id)
                .values(last_attempt_at=now, next_check_at=now + timedelta(minutes=15))
            )
            config = dict(row)
        lease = self.verifier.acquire() if self.verifier else None
        try:
            candidate, identity, proof = self.loader(
                config["repository"],
                config["branch"],
                site_id,
                config["receipt"]["commit_sha"] if automatic and config["receipt"] else None,
            )
            with self.database.begin() as c:
                lock_graph(c)
                site, row = self.checked(c, actor, site_id, generation)
                publication(c, actor, site_id, proposal=True)
                now = c.scalar(select(func.clock_timestamp()))
                if self.base(c, site) != base:
                    raise SourceError("SOURCE_PREVIEW_STALE")
                if row["repository_id"] is None:
                    if row["proof_expires_at"] <= now or not secrets.compare_digest(
                        row["proof_digest"], proof
                    ):
                        raise SourceError("SOURCE_PROOF_REQUIRED", 403)
                elif identity != (row["repository_id"], row["repository_owner_id"]):
                    raise SourceError("SOURCE_IDENTITY_CHANGED", 403)
                if candidate is None:
                    if not automatic or not row["receipt"]:
                        raise SourceError("SOURCE_PREVIEW_REQUIRED")
                    c.execute(
                        update(sources).where(sources.c.site_id == site_id).values(last_error=None)
                    )
                    return {
                        "changed": 0,
                        "writes_performed": False,
                        "commit_sha": row["receipt"]["commit_sha"],
                    }
                url = "https://github.com/" + row["repository"] + ".git"
                summary = publish_on(
                    c, candidate, url, row["origin"], check=True, authority="owner"
                )
                preview_id = uuid4().hex
                c.execute(
                    update(sources)
                    .where(sources.c.site_id == site_id)
                    .values(
                        repository_id=identity[0],
                        repository_owner_id=identity[1],
                        candidate=asdict(candidate),
                        preview_id=preview_id,
                        preview_base=base,
                        preview_expires_at=now + timedelta(minutes=30),
                        last_error=None,
                    )
                )
                if automatic:
                    # Policy was explicitly opted into when the first preview was accepted.
                    if row["policy"] != "auto":
                        raise SourceError("SOURCE_CHANGED")
                    return self._accept(c, actor, site_id, generation, preview_id)
                return {**summary, "preview_id": preview_id, "source_ownership_verified": True}
        except (RootImportError, PublicPointError) as exc:
            with self.database.begin() as c:
                c.execute(
                    update(sources)
                    .where(sources.c.site_id == site_id, sources.c.generation == generation)
                    .values(last_error=exc.code[:64])
                )
            raise
        finally:
            if lease:
                self.verifier.release(lease)

    def accept(self, actor, site_id, generation, preview_id):
        with self.database.begin() as c:
            lock_graph(c)
            return self._accept(c, actor, site_id, generation, preview_id)

    def _accept(self, c, actor, site_id, generation, preview_id):
        site, row = self.checked(c, actor, site_id, generation)
        from .bans import publication

        publication(c, actor, site_id, proposal=True)
        if row["accepted_preview_id"] == preview_id and row["receipt"]:
            return row["receipt"]
        now = c.scalar(select(func.clock_timestamp()))
        if (
            row["preview_id"] != preview_id
            or not row["candidate"]
            or row["preview_expires_at"] <= now
            or row["repository_id"] is None
        ):
            raise SourceError("SOURCE_PREVIEW_EXPIRED")
        if self.base(c, site) != row["preview_base"]:
            raise SourceError("SOURCE_PREVIEW_STALE")
        candidate = restore_candidate(row["candidate"])
        result = publish_on(
            c,
            candidate,
            "https://github.com/" + row["repository"] + ".git",
            row["origin"],
            authority="owner",
        )
        c.execute(
            update(sources)
            .where(sources.c.site_id == site_id)
            .values(
                accepted_preview_id=preview_id,
                receipt=result,
                candidate=None,
                preview_base=None,
                preview_id=None,
                preview_expires_at=None,
                last_error=None,
            )
        )
        return result

    def policy(self, actor, site_id, generation, policy):
        if policy not in ("manual", "auto"):
            raise SourceError("INVALID_UPDATE_POLICY", 422)
        with self.database.begin() as c:
            lock_graph(c)
            self.checked(c, actor, site_id, generation)
            c.execute(update(sources).where(sources.c.site_id == site_id).values(policy=policy))
            c.execute(
                insert(events).values(
                    operation_id="o_" + uuid4().hex,
                    kind="git_source_policy",
                    actor_user_id=actor,
                    site_id=site_id,
                    point_id=site_id,
                    payload={"policy": policy},
                )
            )
        return {"policy": policy}

    def work(self):
        with self.database.begin() as c:
            c.execute(
                update(sources)
                .where(sources.c.preview_expires_at <= func.clock_timestamp())
                .values(candidate=None, preview_base=None, preview_id=None, preview_expires_at=None)
            )
        with self.database.connect() as c:
            row = c.execute(
                select(sources.c.site_id, sources.c.owner_user_id, sources.c.generation)
                .where(
                    sources.c.policy == "auto",
                    sources.c.repository_id.is_not(None),
                    sources.c.receipt.is_not(None),
                    sources.c.next_check_at <= func.clock_timestamp(),
                )
                .order_by(sources.c.next_check_at, sources.c.site_id)
                .limit(1)
            ).one_or_none()
        if row:
            try:
                self.refresh(row.owner_user_id, row.site_id, row.generation, automatic=True)
            except (RootImportError, PublicPointError, SiteClaimError) as exc:
                with self.database.begin() as c:
                    c.execute(
                        update(sources)
                        .where(
                            sources.c.site_id == row.site_id, sources.c.generation == row.generation
                        )
                        .values(
                            next_check_at=func.clock_timestamp() + timedelta(minutes=15),
                            last_error=exc.code[:64],
                        )
                    )
