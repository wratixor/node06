from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import and_, insert, select, update
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from .db import Database
from .home_page import HomePage
from .models import (
    edge_claims,
    events,
    point_edges,
    point_revisions,
    points,
    site_claims,
    site_members,
    sites,
    users,
)
from .site_claims import (
    ClaimMaterial,
    fetch_proof,
    issue_claim,
    normalize_origin,
    validate_proof_document,
)

ALL_SITES_ID = "all-sites"
ALL_SITES_BOOTSTRAP_REVISION = "v_00000000000000000000000000000000"


class SiteRegistryError(RuntimeError):
    code = "SITE_REGISTRY_ERROR"


class SiteNotFoundError(SiteRegistryError):
    code = "SITE_NOT_FOUND"


class SiteConflictError(SiteRegistryError):
    code = "SITE_CONFLICT"


class SitePermissionError(SiteRegistryError):
    code = "SITE_FORBIDDEN"


class SiteAttemptsError(SiteRegistryError):
    code = "SITE_ATTEMPTS_EXCEEDED"


class SiteClaimExpiredError(SiteRegistryError):
    code = "SITE_CLAIM_EXPIRED"


@dataclass(frozen=True)
class PendingSite:
    site_id: str
    claim_id: str
    origin: str
    proof_path: str
    proof_document: str
    expires_at: datetime


@dataclass(frozen=True)
class PublicSite:
    id: str
    origin: str
    state: str
    display_name: str | None
    welcome_source: str
    settings_revision: int
    welcome_revision_id: str
    welcome_body: str
    home_page: dict | None = None


def new_user_id() -> str:
    return f"u_{uuid4().hex}"


def new_site_id() -> str:
    return f"s_{uuid4().hex}"


def new_revision_id() -> str:
    return f"v_{uuid4().hex}"


def new_operation_id() -> str:
    return f"o_{uuid4().hex}"


def new_claim_id() -> str:
    return f"c_{uuid4().hex}"


def new_edge_claim_id() -> str:
    return f"e_{uuid4().hex}"


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


class SiteRegistry:
    """Site lifecycle with optional transaction-bound caller authorization.

    HTTP management supplies a session checker; trusted bootstrap/tests may omit it.
    The service owns
    its transaction boundaries so verification never holds a database transaction open
    while performing the outbound proof fetch.
    """

    def __init__(
        self,
        database: Database,
        *,
        clock: Callable[[], datetime] | None = None,
        authorize_actor: Callable[[Connection, str], None] | None = None,
    ):
        self.database = database
        self.clock = clock or (lambda: datetime.now(UTC))
        self.authorize_actor = authorize_actor

    def _authorize(self, connection: Connection, user_id: str) -> None:
        if self.authorize_actor is not None:
            self.authorize_actor(connection, user_id)
        self._require_active_owner(connection, user_id)

    def create_placeholder_user(self, handle: str) -> str:
        """P02 test/bootstrap helper. P03 replaces this with authenticated account creation."""
        user_id = new_user_id()
        with self.database.begin() as connection:
            connection.execute(insert(users).values(id=user_id, handle=handle, state="active"))
        return user_id

    def create_pending_site(
        self,
        *,
        owner_user_id: str,
        origin: str,
        welcome_body: str,
        display_name: str | None = None,
        now: datetime | None = None,
    ) -> PendingSite:
        normalized = normalize_origin(origin)
        site_id = new_site_id()
        revision_id = new_revision_id()
        claim_id = new_claim_id()
        operation_id = new_operation_id()
        created_at = now or self.clock()
        material: ClaimMaterial = issue_claim(site_id, created_at)

        try:
            with self.database.begin() as connection:
                self._authorize(connection, owner_user_id)
                owner = connection.execute(
                    select(users.c.id)
                    .where(users.c.id == owner_user_id, users.c.state == "active")
                    .with_for_update()
                ).scalar_one_or_none()
                if owner is None:
                    raise SiteRegistryError("Active owner user does not exist.")
                occupied = connection.execute(
                    select(sites.c.id).where(
                        (sites.c.claimed_origin == normalized)
                        | (sites.c.primary_origin == normalized)
                    )
                ).scalar_one_or_none()
                if occupied is not None:
                    raise SiteConflictError("Origin is already claimed or pending verification.")

                connection.execute(
                    insert(points).values(
                        id=site_id,
                        origin="site",
                        author_user_id=owner_user_id,
                        current_revision_id=None,
                        lifecycle="inactive",
                        created_at=created_at,
                        content_updated_at=created_at,
                        last_interaction_at=created_at,
                    )
                )
                connection.execute(
                    insert(point_revisions).values(
                        id=revision_id,
                        point_id=site_id,
                        body=welcome_body,
                        declared_links=[],
                        editor_user_id=owner_user_id,
                        created_at=created_at,
                    )
                )
                connection.execute(
                    update(points)
                    .where(points.c.id == site_id)
                    .values(current_revision_id=revision_id)
                )
                connection.execute(
                    insert(sites).values(
                        id=site_id,
                        owner_user_id=owner_user_id,
                        claimed_origin=normalized,
                        primary_origin=None,
                        state="pending",
                        welcome_source="ui",
                        settings_revision=1,
                        display_name=display_name,
                        theme={},
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
                connection.execute(
                    insert(site_members).values(
                        site_id=site_id, user_id=owner_user_id, role="owner"
                    )
                )
                connection.execute(
                    insert(site_claims).values(
                        id=claim_id,
                        site_id=site_id,
                        origin=normalized,
                        challenge_digest=material.digest,
                        expires_at=material.expires_at,
                        attempt_count=0,
                        created_at=created_at,
                    )
                )
                connection.execute(
                    insert(events).values(
                        operation_id=operation_id,
                        kind="site_claim_created",
                        actor_user_id=owner_user_id,
                        site_id=site_id,
                        point_id=site_id,
                        payload={"origin": normalized},
                        created_at=created_at,
                    )
                )
        except IntegrityError as exc:
            raise SiteConflictError(
                "Origin, handle or site state conflicts with existing data."
            ) from exc

        return PendingSite(
            site_id=site_id,
            claim_id=claim_id,
            origin=normalized,
            proof_path="/node06-verification.txt",
            proof_document=material.document,
            expires_at=material.expires_at,
        )

    def verify_site(
        self,
        site_id: str,
        *,
        actor_user_id: str,
        proof_fetcher: Callable[[str], bytes] = fetch_proof,
        now: datetime | None = None,
        max_attempts: int | None = None,
    ) -> PublicSite:
        # Phase 1 commits the attempt counter before the network request. A failed
        # proof cannot erase its attempt by rolling back the activation transaction.
        with self.database.begin() as connection:
            self._authorize(connection, actor_user_id)
            site = (
                connection.execute(select(sites).where(sites.c.id == site_id).with_for_update())
                .mappings()
                .one_or_none()
            )
            if site is None:
                raise SiteNotFoundError("Site does not exist.")
            if site["owner_user_id"] != actor_user_id:
                raise SitePermissionError("Only the site owner may verify the claim.")
            if site["state"] == "active":
                return self._get_public_site(connection, site_id)
            if site["state"] != "pending":
                raise SiteConflictError("Only pending sites may be activated by a claim.")
            claim = (
                connection.execute(
                    select(site_claims)
                    .where(
                        and_(site_claims.c.site_id == site_id, site_claims.c.verified_at.is_(None))
                    )
                    .with_for_update()
                )
                .mappings()
                .one_or_none()
            )
            if claim is None:
                raise SiteRegistryError("No active verification claim exists.")
            if _as_utc(claim["expires_at"]) <= (now or self.clock()):
                raise SiteClaimExpiredError("Site verification claim has expired.")
            if claim["origin"] != site["claimed_origin"]:
                raise SiteConflictError("Claim does not match the site's origin.")
            if max_attempts is not None and claim["attempt_count"] >= max_attempts:
                raise SiteAttemptsError("Renew the challenge before checking the proof again.")
            connection.execute(
                update(site_claims)
                .where(site_claims.c.id == claim["id"])
                .values(attempt_count=site_claims.c.attempt_count + 1)
            )
            claim_id = claim["id"]
            claim_origin = claim["origin"]
            challenge_digest = claim["challenge_digest"]

        document = proof_fetcher(claim_origin)
        validate_proof_document(document, site_id, challenge_digest)

        # Phase 2 locks and rechecks the same claim, then publishes the site atomically.
        try:
            with self.database.begin() as connection:
                self._authorize(connection, actor_user_id)
                site = (
                    connection.execute(select(sites).where(sites.c.id == site_id).with_for_update())
                    .mappings()
                    .one_or_none()
                )
                claim = (
                    connection.execute(
                        select(site_claims).where(site_claims.c.id == claim_id).with_for_update()
                    )
                    .mappings()
                    .one_or_none()
                )
                if site is None or claim is None:
                    raise SiteNotFoundError("Site verification state no longer exists.")
                if site["owner_user_id"] != actor_user_id:
                    raise SitePermissionError("Only the site owner may verify the claim.")
                if site["state"] == "active":
                    return self._get_public_site(connection, site_id)
                if site["state"] != "pending":
                    raise SiteConflictError("Site was disabled while proof was being checked.")
                if claim["verified_at"] is not None:
                    raise SiteConflictError("Verification claim was already consumed.")
                checked_at = now or self.clock()
                if _as_utc(claim["expires_at"]) <= checked_at:
                    raise SiteClaimExpiredError("Site verification claim has expired.")
                if (
                    claim["origin"] != claim_origin
                    or site["claimed_origin"] != claim_origin
                    or claim["challenge_digest"] != challenge_digest
                ):
                    raise SiteConflictError(
                        "Verification claim changed while proof was being checked."
                    )

                self._ensure_core_directory(connection)
                point_a, point_b = sorted((ALL_SITES_ID, site_id))
                operation_id = new_operation_id()
                connection.execute(
                    update(site_claims)
                    .where(site_claims.c.id == claim_id)
                    .values(verified_at=checked_at)
                )
                connection.execute(
                    update(sites)
                    .where(sites.c.id == site_id)
                    .values(
                        primary_origin=claim_origin,
                        state="active",
                        verified_at=checked_at,
                        updated_at=checked_at,
                    )
                )
                connection.execute(
                    update(points)
                    .where(points.c.id == site_id)
                    .values(lifecycle="active", last_interaction_at=checked_at)
                )
                edge_exists = connection.execute(
                    select(point_edges.c.point_a).where(
                        and_(point_edges.c.point_a == point_a, point_edges.c.point_b == point_b)
                    )
                ).scalar_one_or_none()
                if edge_exists is None:
                    connection.execute(
                        insert(point_edges).values(
                            point_a=point_a, point_b=point_b, created_at=checked_at
                        )
                    )
                claim_exists = connection.execute(
                    select(edge_claims.c.id).where(
                        and_(
                            edge_claims.c.point_a == point_a,
                            edge_claims.c.point_b == point_b,
                            edge_claims.c.claim_kind == "system-site-directory",
                            edge_claims.c.claim_ref == site_id,
                        )
                    )
                ).scalar_one_or_none()
                if claim_exists is None:
                    connection.execute(
                        insert(edge_claims).values(
                            id=new_edge_claim_id(),
                            point_a=point_a,
                            point_b=point_b,
                            claim_kind="system-site-directory",
                            claim_ref=site_id,
                            created_at=checked_at,
                        )
                    )
                connection.execute(
                    insert(events).values(
                        operation_id=operation_id,
                        kind="site_verified",
                        actor_user_id=actor_user_id,
                        site_id=site_id,
                        point_id=site_id,
                        payload={"origin": claim_origin},
                        created_at=checked_at,
                    )
                )
                return self._get_public_site(connection, site_id)
        except IntegrityError as exc:
            raise SiteConflictError(
                "Origin or site activation conflicts with existing state."
            ) from exc

    def get_public_site(self, site_id: str) -> PublicSite:
        with self.database.connect() as connection:
            return self._get_public_site(connection, site_id)

    def managed_site(self, site_id: str, actor_user_id: str) -> dict:
        with self.database.begin() as connection:
            self._authorize(connection, actor_user_id)
            return self._managed_site(connection, site_id, actor_user_id)

    def list_owned(self, actor_user_id: str, *, after: str = "", limit: int = 30) -> list[dict]:
        with self.database.begin() as connection:
            self._authorize(connection, actor_user_id)
            ids = (
                connection.execute(
                    select(sites.c.id)
                    .where(sites.c.owner_user_id == actor_user_id, sites.c.id > after)
                    .order_by(sites.c.id)
                    .limit(limit)
                )
                .scalars()
                .all()
            )
            return [self._managed_site(connection, site_id, actor_user_id) for site_id in ids]

    @staticmethod
    def _managed_site(connection: Connection, site_id: str, actor_user_id: str) -> dict:
        site = (
            connection.execute(select(sites).where(sites.c.id == site_id).with_for_update())
            .mappings()
            .one_or_none()
        )
        if site is None:
            raise SiteNotFoundError("Site does not exist.")
        if site["owner_user_id"] != actor_user_id:
            raise SitePermissionError("Only the owner may manage this site.")
        revision = (
            connection.execute(
                select(points.c.current_revision_id, point_revisions.c.body)
                .join(point_revisions, points.c.current_revision_id == point_revisions.c.id)
                .where(points.c.id == site_id)
            )
            .mappings()
            .one()
        )
        claim = (
            connection.execute(select(site_claims).where(site_claims.c.site_id == site_id))
            .mappings()
            .one()
        )
        return {
            "id": site["id"],
            "origin": site["claimed_origin"],
            "state": site["state"],
            "display_name": site["display_name"],
            "theme": site["theme"],
            "home_page": site["home_page"],
            "welcome_source": site["welcome_source"],
            "settings_revision": site["settings_revision"],
            "welcome_revision_id": revision["current_revision_id"],
            "welcome_body": revision["body"],
            "claim_id": claim["id"],
            "claim_expires_at": claim["expires_at"],
            "attempt_count": claim["attempt_count"],
        }

    def renew_claim(self, site_id: str, actor_user_id: str, expected_claim_id: str) -> PendingSite:
        now = self.clock()
        material = issue_claim(site_id, now)
        claim_id = new_claim_id()
        with self.database.begin() as connection:
            self._authorize(connection, actor_user_id)
            site = self._managed_site(connection, site_id, actor_user_id)
            if site["state"] != "pending" or site["claim_id"] != expected_claim_id:
                raise SiteConflictError("Claim or site state has changed.")
            connection.execute(
                update(site_claims)
                .where(site_claims.c.id == expected_claim_id)
                .values(
                    id=claim_id,
                    challenge_digest=material.digest,
                    expires_at=material.expires_at,
                    created_at=now,
                    attempt_count=0,
                )
            )
            connection.execute(
                insert(events).values(
                    operation_id=new_operation_id(),
                    kind="site_claim_renewed",
                    actor_user_id=actor_user_id,
                    site_id=site_id,
                    point_id=site_id,
                    payload={"claim_id": claim_id},
                    created_at=now,
                )
            )
        return PendingSite(
            site_id,
            claim_id,
            site["origin"],
            "/node06-verification.txt",
            material.document,
            material.expires_at,
        )

    def update_settings(
        self,
        site_id: str,
        actor_user_id: str,
        *,
        expected_settings_revision: int,
        expected_welcome_revision: str,
        display_name: str | None,
        theme: dict,
        welcome_body: str,
    ) -> dict:
        with self.database.begin() as connection:
            self._authorize(connection, actor_user_id)
            site = self._managed_site(connection, site_id, actor_user_id)
            if (
                site["settings_revision"] != expected_settings_revision
                or site["welcome_revision_id"] != expected_welcome_revision
            ):
                raise SiteConflictError("Site settings or welcome text changed; reload first.")
            if site["state"] not in ("pending", "active") or site["welcome_source"] != "ui":
                raise SiteConflictError("This site's welcome cannot be edited through this API.")
            body_changed = site["welcome_body"] != welcome_body
            if not body_changed and site["display_name"] == display_name and site["theme"] == theme:
                return site
            now = self.clock()
            revision_id = site["welcome_revision_id"]
            if body_changed:
                revision_id = new_revision_id()
                connection.execute(
                    insert(point_revisions).values(
                        id=revision_id,
                        point_id=site_id,
                        body=welcome_body,
                        declared_links=[],
                        editor_user_id=actor_user_id,
                        created_at=now,
                    )
                )
                connection.execute(
                    update(points)
                    .where(points.c.id == site_id)
                    .values(
                        current_revision_id=revision_id,
                        content_updated_at=now,
                        last_interaction_at=now,
                    )
                )
            connection.execute(
                update(sites)
                .where(sites.c.id == site_id)
                .values(
                    display_name=display_name,
                    theme=theme,
                    settings_revision=site["settings_revision"] + 1,
                    updated_at=now,
                )
            )
            connection.execute(
                insert(events).values(
                    operation_id=new_operation_id(),
                    kind="site_settings_updated",
                    actor_user_id=actor_user_id,
                    site_id=site_id,
                    point_id=site_id,
                    payload={"welcome_revision_id": revision_id, "body_changed": body_changed},
                    created_at=now,
                )
            )
            return self._managed_site(connection, site_id, actor_user_id)

    def update_home_page(
        self,
        site_id: str,
        actor_user_id: str,
        *,
        expected_settings_revision: int,
        home_page: dict | None,
    ) -> dict:
        # Validate at the service boundary too, not only through the HTTP model.
        value = HomePage.model_validate(home_page).model_dump() if home_page is not None else None
        with self.database.begin() as connection:
            self._authorize(connection, actor_user_id)
            site = self._managed_site(connection, site_id, actor_user_id)
            if site["settings_revision"] != expected_settings_revision:
                raise SiteConflictError(
                    "Site settings changed; compare the current home page first."
                )
            if site["state"] not in ("pending", "active"):
                raise SiteConflictError("Inactive site cannot be edited.")
            if site["home_page"] == value:
                return site
            now = self.clock()
            connection.execute(
                update(sites)
                .where(sites.c.id == site_id)
                .values(
                    home_page=value, settings_revision=site["settings_revision"] + 1, updated_at=now
                )
            )
            connection.execute(
                insert(events).values(
                    operation_id=new_operation_id(),
                    kind="site_home_updated",
                    actor_user_id=actor_user_id,
                    site_id=site_id,
                    point_id=site_id,
                    payload={"block_count": len(value["blocks"]) if value else None},
                    created_at=now,
                )
            )
            return self._managed_site(connection, site_id, actor_user_id)

    @staticmethod
    def _require_active_owner(connection: Connection, user_id: str) -> None:
        owner = connection.execute(
            select(users.c.id)
            .where(users.c.id == user_id, users.c.state == "active")
            .with_for_update()
        ).scalar_one_or_none()
        if owner is None:
            raise SiteRegistryError("Active owner user does not exist.")

    @staticmethod
    def _get_public_site(connection: Connection, site_id: str) -> PublicSite:
        row = (
            connection.execute(
                select(
                    sites.c.id,
                    sites.c.primary_origin,
                    sites.c.state,
                    sites.c.display_name,
                    sites.c.welcome_source,
                    sites.c.home_page,
                    sites.c.settings_revision,
                    points.c.current_revision_id,
                    point_revisions.c.body,
                )
                .join(points, points.c.id == sites.c.id)
                .join(point_revisions, point_revisions.c.id == points.c.current_revision_id)
                .where(sites.c.id == site_id)
            )
            .mappings()
            .one_or_none()
        )
        if row is None or row["state"] != "active" or row["primary_origin"] is None:
            raise SiteNotFoundError("Active site does not exist.")
        return PublicSite(
            id=row["id"],
            origin=row["primary_origin"],
            state=row["state"],
            display_name=row["display_name"],
            welcome_source=row["welcome_source"],
            settings_revision=row["settings_revision"],
            welcome_revision_id=row["current_revision_id"],
            welcome_body=row["body"],
            home_page=row["home_page"],
        )

    @staticmethod
    def _ensure_core_directory(connection: Connection) -> None:
        if connection.execute(
            select(points.c.id).where(points.c.id == ALL_SITES_ID)
        ).scalar_one_or_none():
            return
        now = datetime.now(UTC)
        connection.execute(
            insert(points).values(
                id=ALL_SITES_ID,
                origin="root",
                current_revision_id=None,
                lifecycle="active",
                created_at=now,
                content_updated_at=now,
                last_interaction_at=now,
            )
        )
        connection.execute(
            insert(point_revisions).values(
                id=ALL_SITES_BOOTSTRAP_REVISION,
                point_id=ALL_SITES_ID,
                body="All sites / Все сайты",
                declared_links=[],
                editor_user_id=None,
                created_at=now,
            )
        )
        connection.execute(
            update(points)
            .where(points.c.id == ALL_SITES_ID)
            .values(current_revision_id=ALL_SITES_BOOTSTRAP_REVISION)
        )
