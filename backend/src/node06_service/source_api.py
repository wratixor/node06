"""Private, first-party owner source management; never available on embed origin."""

from typing import Annotated, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, StringConstraints

from .site_api import SiteID, manager
from .source_service import Sources
from .verifier import ProofVerifier

router = APIRouter(prefix="/api/v1/sites")
Generation = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{32}$")]


class Configure(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    repository: Annotated[str, StringConstraints(max_length=256)]
    branch: Annotated[str, StringConstraints(max_length=128)] = "main"
    policy: Literal["manual", "auto"] = "manual"
    expected_generation: Generation | None = None
    rights_confirmed: Literal[True]


class Preview(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    generation: Generation


class Accept(Preview):
    preview_id: Generation
    accept_git_welcome: Literal[True]


class Policy(Preview):
    policy: Literal["manual", "auto"]


def service(request, mutation=True):
    registry, auth, actor = manager(request, mutation=mutation)
    if mutation:
        auth._limit("source-owner", actor.user_id, 12, 3600)
    settings = request.app.state.settings.model_copy(update={"verifier_seconds": 30})
    kwargs = {
        "authorize": registry.authorize_actor,
        "verifier": ProofVerifier(request.app.state.database, settings),
    }
    if hasattr(request.app.state, "source_loader"):
        kwargs["loader"] = request.app.state.source_loader
    return Sources(request.app.state.database, **kwargs), actor.user_id


@router.get("/{site_id}/source")
def status(site_id: SiteID, request: Request):
    sources, actor = service(request, False)
    return sources.status(actor, site_id)


@router.put("/{site_id}/source")
def configure(site_id: SiteID, payload: Configure, request: Request):
    sources, actor = service(request)
    return sources.configure(actor, site_id, **payload.model_dump(exclude={"rights_confirmed"}))


@router.post("/{site_id}/source/preview")
def preview(site_id: SiteID, payload: Preview, request: Request):
    sources, actor = service(request)
    return sources.refresh(actor, site_id, payload.generation)


@router.post("/{site_id}/source/accept")
def accept(site_id: SiteID, payload: Accept, request: Request):
    sources, actor = service(request)
    return sources.accept(actor, site_id, payload.generation, payload.preview_id)


@router.put("/{site_id}/source/policy")
def policy(site_id: SiteID, payload: Policy, request: Request):
    sources, actor = service(request)
    return sources.policy(actor, site_id, payload.generation, payload.policy)
