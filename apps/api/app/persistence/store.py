import secrets
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .join_policy import email_domain
from .models import (
    Account,
    Organization,
    OrganizationAllowedEmail,
    OrganizationEmailDomain,
    OrganizationMember,
    User,
)


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
    account_type: str = "candidate"
    email_verified: bool = False
    image: str | None = None


@dataclass(frozen=True)
class JoinedOrganization:
    id: str
    name: str
    role: str


class Store(Protocol):
    async def register(
        self, name: str, email: str, password_hash: str, account_type: str = "candidate"
    ) -> UserRecord: ...

    async def credentials(self, email: str) -> tuple[UserRecord, str]: ...

    async def user(self, user_id: str) -> UserRecord: ...

    async def apply_join_policies(self, user_id: str, email: str) -> list[JoinedOrganization]: ...


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

    def sessions(self) -> async_sessionmaker[AsyncSession]:
        return self._sessions

    async def register(
        self, name: str, email: str, password_hash: str, account_type: str = "candidate"
    ) -> UserRecord:
        now = datetime.now(UTC)
        user = User(
            id=_new_id(),
            name=name,
            email=email,
            account_type=account_type,
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
                session.add(user)
                await session.flush()
                session.add(account)
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

    async def apply_join_policies(self, user_id: str, email: str) -> list[JoinedOrganization]:
        domain = email_domain(email)
        async with self._sessions.begin() as session:
            domain_org_ids = select(OrganizationEmailDomain.organization_id).where(
                OrganizationEmailDomain.domain == domain
            )
            email_org_ids = select(OrganizationAllowedEmail.organization_id).where(
                OrganizationAllowedEmail.email == email
            )
            organizations = (
                (
                    await session.execute(
                        select(Organization)
                        .where(
                            Organization.id.in_(domain_org_ids) | Organization.id.in_(email_org_ids)
                        )
                        .order_by(Organization.created_at)
                    )
                )
                .scalars()
                .all()
            )
            joined_ids = set(
                (
                    await session.execute(
                        select(OrganizationMember.organization_id).where(
                            OrganizationMember.user_id == user_id
                        )
                    )
                ).scalars()
            )
            # An employer user belongs to at most one organization, so only
            # the first matching organization claims the registration.
            joined: list[JoinedOrganization] = []
            for organization in organizations:
                if organization.id in joined_ids:
                    continue
                session.add(
                    OrganizationMember(
                        id=_new_id(),
                        organization_id=organization.id,
                        user_id=user_id,
                        role=organization.default_member_role,
                    )
                )
                joined.append(
                    JoinedOrganization(
                        id=organization.id,
                        name=organization.name,
                        role=organization.default_member_role,
                    )
                )
                break
            return joined


def _to_record(user: User) -> UserRecord:
    return UserRecord(
        id=user.id,
        name=user.name,
        email=user.email,
        account_type=user.account_type,
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
