import secrets
from dataclasses import asdict
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel, ConfigDict, SecretStr, StringConstraints, field_validator

from .auth import SESSION_COOKIE, AuthError, AuthService, csrf_for

router = APIRouter(prefix="/api/v1")
Handle = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9_-]{2,63}$", strict=True)]


class Credentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    handle: Handle
    password: SecretStr

    @field_validator("password")
    @classmethod
    def password_length(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if not 12 <= len(raw) <= 128 or len(raw.encode()) > 512:
            raise ValueError("Password must contain 12..128 characters and at most 512 UTF-8 bytes")
        return value


class Recovery(Credentials):
    recovery_code: SecretStr

    @field_validator("recovery_code")
    @classmethod
    def recovery_shape(cls, value: SecretStr) -> SecretStr:
        raw = value.get_secret_value()
        if len(raw) != 48 or not raw.startswith("n06r_"):
            raise ValueError("Invalid recovery code shape")
        return value


def service(request: Request) -> AuthService:
    if not request.app.state.database.configured:
        raise AuthError("DATABASE_NOT_CONFIGURED", 503)
    return AuthService(request.app.state.database, request.app.state.settings)


def configured_origin(request: Request) -> str:
    if request.url.scheme != "https":
        raise AuthError("HTTPS_REQUIRED", 403)
    expected = request.app.state.settings.management_origin
    try:
        parts = urlsplit(expected or "")
    except ValueError:
        raise AuthError("AUTH_ORIGIN_NOT_CONFIGURED", 503) from None
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.password
        or parts.path
        or parts.query
        or parts.fragment
    ):
        raise AuthError("AUTH_ORIGIN_NOT_CONFIGURED", 503)
    return expected


def trusted_origin(request: Request) -> None:
    expected = configured_origin(request)
    if request.headers.get("origin") != expected:
        raise AuthError("ORIGIN_FORBIDDEN", 403)
    if request.method not in ("GET", "DELETE"):
        if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
            raise AuthError("JSON_REQUIRED", 415)


def authenticated_mutation(request: Request) -> tuple[AuthService, str]:
    trusted_origin(request)
    auth = service(request)
    token = request.cookies.get(SESSION_COOKIE)
    auth.authenticate(token)
    supplied = request.headers.get("x-csrf-token", "")
    if not secrets.compare_digest(supplied.encode(), csrf_for(token).encode()):
        raise AuthError("CSRF_REQUIRED", 403)
    return auth, token


@router.post("/auth/register", status_code=201)
def register(payload: Credentials, request: Request):
    trusted_origin(request)
    result = service(request).register(
        payload.handle, payload.password.get_secret_value(), request.client.host
    )
    return {
        "account_created": True,
        **asdict(result.identity),
        "recovery_code": result.recovery_code,
    }


@router.post("/auth/recover")
def recover(payload: Recovery, request: Request, response: Response):
    trusted_origin(request)
    replacement = service(request).recover(
        payload.handle,
        payload.password.get_secret_value(),
        payload.recovery_code.get_secret_value(),
        request.client.host,
    )
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
    return {"password_changed": True, "recovery_code": replacement}


@router.post("/auth/login")
def login(payload: Credentials, request: Request, response: Response):
    trusted_origin(request)
    auth = service(request)
    result = auth.login(
        payload.handle,
        payload.password.get_secret_value(),
        request.client.host,
        request.cookies.get(SESSION_COOKIE),
    )
    response.set_cookie(
        SESSION_COOKIE,
        result.token,
        max_age=auth.settings.session_hours * 3600,
        secure=True,
        httponly=True,
        samesite="strict",
        path="/",
    )
    return {**asdict(result.identity), "csrf_token": csrf_for(result.token)}


@router.get("/me")
def me(request: Request):
    expected = configured_origin(request)
    if request.headers.get("origin") not in (None, expected):
        raise AuthError("ORIGIN_FORBIDDEN", 403)
    token = request.cookies.get(SESSION_COOKIE)
    identity = service(request).authenticate(token)
    return {**asdict(identity), "csrf_token": csrf_for(token)}


@router.delete("/auth/session", status_code=204)
def logout(request: Request, response: Response):
    auth, token = authenticated_mutation(request)
    auth.logout(token)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")


@router.delete("/auth/sessions", status_code=204)
def logout_all(request: Request, response: Response):
    auth, token = authenticated_mutation(request)
    auth.logout(token, all_sessions=True)
    response.delete_cookie(SESSION_COOKIE, path="/", secure=True, httponly=True, samesite="strict")
