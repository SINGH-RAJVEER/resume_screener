from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)

from .models import Account, User


class NotFoundError(Exception):
    pass


class EmailAlreadyUsedError(Exception):
    pass


@dataclass(frozen=True)
class UserRecord:
    id: str
    name: str
    email: str
    created_at: datetime
    updated_at: datetime
    email_verified: bool = False
    image: str | None = None


class Store(Protocol):
    async def register(self, name: str, email: str, password_hash: str) -> UserRecord: ...

    async def credentials(self, email: str) -> tuple[UserRecord, str]: ...

    async def user(self, user_id: str) -> UserRecord: ...


def database_url_for_asyncpg(url: str) -> str:
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    if url.startswith("postgres://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgres://")
    return url


def _new_id() -> str:
    return secrets.token_urlsafe(18)


class SQLAlchemyStore:
    def __init__(self, engine: AsyncEngine) -> None:
        self._sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def register(self, name: str, email: str, password_hash: str) -> UserRecord:
        now = datetime.now(UTC)
        user = User(
            id=_new_id(),
            name=name,
            email=email,
            email_verified=False,
            created_at=now,
            updated_at=now,
        )
        account = Account(
            id=_new_id(),
            account_id=email,
            provider_id="credential",
            user_id=user.id,
            password=password_hash,
            created_at=now,
            updated_at=now,
        )
        try:
            async with self._sessions.begin() as session:
                session.add_all([user, account])
        except IntegrityError as error:
            if _is_email_conflict(error):
                raise EmailAlreadyUsedError from error
            raise
        return _to_record(user)

    async def credentials(self, email: str) -> tuple[UserRecord, str]:
        async with self._sessions() as session:
            result = await session.execute(
                select(User, Account.password)
                .join(Account, (Account.user_id == User.id) & (Account.provider_id == "credential"))
                .where(User.email == email)
            )
            row = result.one_or_none()
        if row is None or row[1] is None:
            raise NotFoundError
        return _to_record(row[0]), row[1]

    async def user(self, user_id: str) -> UserRecord:
        async with self._sessions() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            user = result.scalar_one_or_none()
        if user is None:
            raise NotFoundError
        return _to_record(user)


def _to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        name=user.name,
        email=user.email,
        email_verified=user.email_verified,
        image=user.image,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def create_engine_for_url(database_url: str) -> AsyncEngine:
    return create_async_engine(database_url_for_asyncpg(database_url), pool_pre_ping=True)


def _is_email_conflict(error: IntegrityError) -> bool:
    cause = getattr(error.orig, "__cause__", None)
    constraint = getattr(cause, "constraint_name", None)
    return constraint in {"uq_user_email", "user_email_key"}
