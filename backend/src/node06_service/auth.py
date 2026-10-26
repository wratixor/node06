from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from threading import BoundedSemaphore

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from sqlalchemy import case, insert, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import IntegrityError

from .config import Settings
from .db import Database
from .models import account_credentials, auth_limits, sessions, users
from .site_registry import new_user_id

# Explicit Argon2id parameters, not library defaults that may change on upgrade.
PASSWORD_HASHER = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=1, type=Type.ID)
DUMMY_HASH = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
SESSION_COOKIE = "__Host-node06-session"
PASSWORD_SLOTS = BoundedSemaphore(2)


class AuthError(RuntimeError):
    def __init__(self, code: str, status: int = 401, retry_after: int | None = None):
        self.code = code
        self.status = status
        self.retry_after = retry_after
        super().__init__(code)


@contextmanager
def password_slot():
    # Per-process memory guard, not a substitute for durable per-IP/account limits.
    if not PASSWORD_SLOTS.acquire(blocking=False):
        raise AuthError("AUTH_BUSY", 503, 1)
    try:
        yield
    finally:
        PASSWORD_SLOTS.release()


def hash_password(password: str) -> str:
    with password_slot():
        return PASSWORD_HASHER.hash(password)


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def csrf_for(token: str) -> str:
    return digest(f"node06-csrf-v1:{token}")


@dataclass(frozen=True)
class Identity:
    user_id: str
    handle: str


@dataclass(frozen=True)
class Login:
    identity: Identity
    token: str = field(repr=False)
    expires_at: datetime


@dataclass(frozen=True)
class Registration:
    identity: Identity
    recovery_code: str = field(repr=False)


class AuthService:
    def __init__(
        self, database: Database, settings: Settings, *, clock: Callable[[], datetime] | None = None
    ):
        self.database = database
        self.settings = settings
        self.clock = clock or (lambda: datetime.now(UTC))

    def _limit(self, scope: str, value: str, maximum: int, seconds: int) -> None:
        now = self.clock()
        resets_at = now + timedelta(seconds=seconds)
        expired = auth_limits.c.resets_at <= now
        statement = pg_insert(auth_limits).values(
            key=digest(f"{scope}:{value}"), count=1, resets_at=resets_at
        )
        statement = statement.on_conflict_do_update(
            index_elements=[auth_limits.c.key],
            set_={
                "count": case((expired, 1), else_=auth_limits.c.count + 1),
                "resets_at": case((expired, resets_at), else_=auth_limits.c.resets_at),
            },
            where=expired | (auth_limits.c.count < maximum),
        ).returning(auth_limits.c.count)
        with self.database.begin() as connection:
            allowed = connection.execute(statement).scalar_one_or_none()
        if allowed is None:
            raise AuthError("AUTH_RATE_LIMITED", 429, seconds)

    def register(self, handle: str, password: str, ip: str) -> Registration:
        self._limit("register-ip", ip, self.settings.registration_per_hour, 3600)
        password_hash = hash_password(password)
        recovery_code = f"n06r_{secrets.token_urlsafe(32)}"
        user_id = new_user_id()
        try:
            with self.database.begin() as connection:
                connection.execute(insert(users).values(id=user_id, handle=handle, state="active"))
                connection.execute(
                    insert(account_credentials).values(
                        user_id=user_id,
                        password_hash=password_hash,
                        recovery_digest=digest(recovery_code),
                        updated_at=self.clock(),
                    )
                )
        except IntegrityError as exc:
            raise AuthError("ACCOUNT_CONFLICT", 409) from exc
        return Registration(Identity(user_id, handle), recovery_code)

    def recover(self, handle: str, password: str, recovery_code: str, ip: str) -> str:
        self._limit("recover-ip", ip, self.settings.login_per_minute, 60)
        self._limit("recover-account", handle, self.settings.account_login_per_minute, 60)
        supplied_digest = digest(recovery_code)
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(users.c.id, users.c.state, account_credentials.c.recovery_digest)
                    .join(account_credentials, account_credentials.c.user_id == users.c.id)
                    .where(users.c.handle == handle)
                )
                .mappings()
                .one_or_none()
            )
        expected = row["recovery_digest"] if row else "0" * 64
        valid = secrets.compare_digest(supplied_digest, expected)
        if not valid or row is None or row["state"] != "active":
            raise AuthError("INVALID_RECOVERY")
        password_hash = hash_password(password)
        replacement = f"n06r_{secrets.token_urlsafe(32)}"
        now = self.clock()
        with self.database.begin() as connection:
            state = connection.execute(
                select(users.c.state).where(users.c.id == row["id"]).with_for_update()
            ).scalar_one()
            current = connection.execute(
                select(account_credentials.c.recovery_digest)
                .where(account_credentials.c.user_id == row["id"])
                .with_for_update()
            ).scalar_one()
            if state != "active" or not secrets.compare_digest(current, supplied_digest):
                raise AuthError("INVALID_RECOVERY")
            connection.execute(
                update(account_credentials)
                .where(account_credentials.c.user_id == row["id"])
                .values(
                    password_hash=password_hash, recovery_digest=digest(replacement), updated_at=now
                )
            )
            connection.execute(
                update(sessions).where(sessions.c.user_id == row["id"]).values(revoked_at=now)
            )
        return replacement

    def login(self, handle: str, password: str, ip: str, old_token: str | None = None) -> Login:
        self._limit("login-ip", ip, self.settings.login_per_minute, 60)
        self._limit("login-account", handle, self.settings.account_login_per_minute, 60)
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(
                        users.c.id,
                        users.c.handle,
                        users.c.state,
                        account_credentials.c.password_hash,
                    )
                    .join(account_credentials, account_credentials.c.user_id == users.c.id)
                    .where(users.c.handle == handle)
                )
                .mappings()
                .one_or_none()
            )
        stored_hash = row["password_hash"] if row else DUMMY_HASH
        try:
            with password_slot():
                PASSWORD_HASHER.verify(stored_hash, password)
        except (VerificationError, InvalidHashError):
            raise AuthError("INVALID_CREDENTIALS") from None
        if row is None or row["state"] != "active":
            raise AuthError("INVALID_CREDENTIALS")
        token = secrets.token_urlsafe(32)
        now = self.clock()
        expires_at = now + timedelta(hours=self.settings.session_hours)
        with self.database.begin() as connection:
            # Lock order is user -> credential -> session everywhere in auth.
            active = connection.execute(
                select(users.c.state).where(users.c.id == row["id"]).with_for_update()
            ).scalar_one()
            current_hash = connection.execute(
                select(account_credentials.c.password_hash)
                .where(account_credentials.c.user_id == row["id"])
                .with_for_update()
            ).scalar_one()
            if active != "active" or current_hash != stored_hash:
                raise AuthError("INVALID_CREDENTIALS")
            if old_token:
                connection.execute(
                    update(sessions)
                    .where(sessions.c.digest == digest(old_token), sessions.c.user_id == row["id"])
                    .values(revoked_at=now)
                )
            connection.execute(
                insert(sessions).values(
                    digest=digest(token), user_id=row["id"], created_at=now, expires_at=expires_at
                )
            )
        return Login(Identity(row["id"], row["handle"]), token, expires_at)

    def authenticate(self, token: str | None) -> Identity:
        if not token or len(token) != 43:
            raise AuthError("AUTH_REQUIRED")
        with self.database.connect() as connection:
            row = (
                connection.execute(
                    select(users.c.id, users.c.handle)
                    .join(sessions, sessions.c.user_id == users.c.id)
                    .where(
                        sessions.c.digest == digest(token),
                        sessions.c.revoked_at.is_(None),
                        sessions.c.expires_at > self.clock(),
                        users.c.state == "active",
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise AuthError("AUTH_REQUIRED")
        return Identity(row["id"], row["handle"])

    def authorize_session(self, connection: Connection, token: str, user_id: str) -> Identity:
        """Authorize within a mutation transaction; lock user before session/site rows."""
        user = (
            connection.execute(
                select(users.c.id, users.c.handle)
                .where(users.c.id == user_id, users.c.state == "active")
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        session = connection.execute(
            select(sessions.c.digest)
            .where(
                sessions.c.digest == digest(token),
                sessions.c.user_id == user_id,
                sessions.c.revoked_at.is_(None),
                sessions.c.expires_at > self.clock(),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if user is None or session is None:
            raise AuthError("AUTH_REQUIRED")
        if self.settings.management_origin:
            from sqlalchemy import text

            connection.execute(
                text("SELECT set_config('node06.profile_origin', :origin, true)"),
                {"origin": self.settings.management_origin},
            )
        return Identity(user["id"], user["handle"])

    def logout(self, token: str, *, all_sessions: bool = False) -> None:
        identity = self.authenticate(token)
        now = self.clock()
        with self.database.begin() as connection:
            active = connection.execute(
                select(users.c.id)
                .where(users.c.id == identity.user_id, users.c.state == "active")
                .with_for_update()
            ).scalar_one_or_none()
            current = connection.execute(
                select(sessions.c.digest)
                .where(
                    sessions.c.digest == digest(token),
                    sessions.c.revoked_at.is_(None),
                    sessions.c.expires_at > now,
                )
                .with_for_update()
            ).scalar_one_or_none()
            if active is None or current is None:
                raise AuthError("AUTH_REQUIRED")
            condition = (
                sessions.c.user_id == identity.user_id
                if all_sessions
                else (sessions.c.digest == digest(token))
            )
            connection.execute(update(sessions).where(condition).values(revoked_at=now))
