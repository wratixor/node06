from dataclasses import asdict
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, field_validator

from .auth import SESSION_COOKIE, AuthError
from .auth_api import authenticated_mutation, configured_origin, service
from .site_registry import SiteRegistry
from .verifier import ProofVerifier

router = APIRouter(prefix="/api/v1")
SiteID = Annotated[str, StringConstraints(pattern=r"^s_[0-9a-f]{32}$")]
ClaimID = Annotated[str, StringConstraints(pattern=r"^c_[0-9a-f]{32}$")]
RevisionID = Annotated[str, StringConstraints(pattern=r"^v_[0-9a-f]{32}$")]
Color = Annotated[
    str, StringConstraints(pattern=r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6})$", strict=True)
]


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")
    bg: Color | None = None
    text: Color | None = None
    accent: Color | None = None
    panel: Color | None = None
    border: Color | None = None
    radius: Annotated[int, Field(strict=True, ge=0, le=16)] | None = None
    font: Literal["system", "serif", "mono"] | None = None
    density: Literal["normal", "compact"] | None = None


class Welcome(BaseModel):
    model_config = ConfigDict(extra="forbid")
    display_name: Annotated[str, StringConstraints(strict=True, max_length=160)] | None = None
    welcome_body: Annotated[str, StringConstraints(strict=True, min_length=1, max_length=8192)]

    @field_validator("welcome_body")
    @classmethod
    def validate_welcome(cls, value: str) -> str:
        if len(value.encode()) > 32768:
            raise ValueError("Welcome body exceeds 32 KiB")
        if "md://" in value:
            raise ValueError("Semantic welcome links require the future point editor")
        return value


class CreateSite(Welcome):
    origin: Annotated[str, StringConstraints(strict=True, max_length=512)]


class SettingsUpdate(Welcome):
    expected_settings_revision: Annotated[int, Field(strict=True, ge=1)]
    expected_welcome_revision: RevisionID
    theme: Theme


class Renewal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_claim_id: ClaimID


class VerifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.get("/ui-config")
def ui_config(request: Request):
    manager(request, mutation=False)
    return {"embed_origin": request.app.state.settings.embed_origin}


def manager(request: Request, *, mutation: bool = True):
    if mutation:
        auth, token = authenticated_mutation(request)
    else:
        expected = configured_origin(request)
        if request.headers.get("origin") not in (None, expected):
            raise AuthError("ORIGIN_FORBIDDEN", 403)
        auth = service(request)
        token = request.cookies.get(SESSION_COOKIE)
    actor = auth.authenticate(token)
    registry = SiteRegistry(
        request.app.state.database,
        authorize_actor=lambda connection, user_id: auth.authorize_session(
            connection, token, user_id
        ),
    )
    return registry, auth, actor


@router.post("/sites", status_code=201)
def create_site(payload: CreateSite, request: Request):
    registry, auth, actor = manager(request)
    settings = request.app.state.settings
    auth._limit("site-create-owner", actor.user_id, settings.site_creations_per_hour, 3600)
    auth._limit("site-create-ip", request.client.host, settings.site_creations_per_hour, 3600)
    return asdict(registry.create_pending_site(owner_user_id=actor.user_id, **payload.model_dump()))


@router.get("/me/sites")
def owned_sites(
    request: Request,
    after: Annotated[str, Query(pattern=r"^(?:s_[0-9a-f]{32})?$")] = "",
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
):
    registry, _auth, actor = manager(request, mutation=False)
    page = registry.list_owned(actor.user_id, after=after, limit=limit + 1)
    return {
        "items": page[:limit],
        "next_cursor": page[limit - 1]["id"] if len(page) > limit else None,
    }


@router.get("/sites/{site_id}/manage")
def manage_site(site_id: SiteID, request: Request):
    registry, _auth, actor = manager(request, mutation=False)
    return registry.managed_site(site_id, actor.user_id)


@router.post("/sites/{site_id}/claim/renew")
def renew_site_claim(site_id: SiteID, payload: Renewal, request: Request):
    registry, auth, actor = manager(request)
    auth._limit(
        "site-renew-owner", actor.user_id, request.app.state.settings.site_renewals_per_hour, 3600
    )
    return asdict(registry.renew_claim(site_id, actor.user_id, payload.expected_claim_id))


@router.post("/sites/{site_id}/verify")
def verify_site(site_id: SiteID, _payload: VerifyRequest, request: Request):
    registry, auth, actor = manager(request)
    settings = request.app.state.settings
    auth._limit("site-verify-owner", actor.user_id, settings.site_verifications_per_minute, 60)
    auth._limit("site-verify-ip", request.client.host, settings.site_verifications_per_minute, 60)
    current = registry.managed_site(site_id, actor.user_id)
    if current["state"] == "active":
        return asdict(registry.verify_site(site_id, actor_user_id=actor.user_id))
    # Admission precedes the durable attempt, so overload does not burn a challenge.
    verifier = ProofVerifier(request.app.state.database, settings)
    with verifier.admitted() as fetch:
        return asdict(
            registry.verify_site(
                site_id,
                actor_user_id=actor.user_id,
                proof_fetcher=fetch,
                max_attempts=settings.claim_max_attempts,
            )
        )


@router.patch("/sites/{site_id}")
def update_site(site_id: SiteID, payload: SettingsUpdate, request: Request):
    registry, _auth, actor = manager(request)
    return registry.update_settings(
        site_id,
        actor.user_id,
        **payload.model_dump(exclude={"theme"}),
        theme=payload.theme.model_dump(exclude_none=True),
    )
