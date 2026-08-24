from collections.abc import AsyncGenerator, Sequence
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import cast

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import FromClause, Table, select
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import StaticPool

from app.auth import AuthService
from app.core.config import Settings
from app.main import create_app
from app.persistence.models import (
    Account,
    Base,
    Organization,
    OrganizationAllowedEmail,
    OrganizationEmailDomain,
    OrganizationMember,
    User,
)
from app.persistence.store import JoinedOrganization, SQLAlchemyStore, UserRecord

SECRET = "test-secret-that-is-at-least-32-characters"
SETTINGS = Settings(
    database_url="postgresql://unused/resume_screener",
    web_url="http://localhost:3000",
    jwt_secret=SECRET,
    jwt_ttl=timedelta(days=1),
)

POLICY_TABLES: Sequence[FromClause] = [
    User.__table__,
    Account.__table__,
    Organization.__table__,
    OrganizationMember.__table__,
    OrganizationEmailDomain.__table__,
    OrganizationAllowedEmail.__table__,
]

pytestmark = pytest.mark.asyncio


def make_user(user_id: str, email: str, account_type: str = "employer") -> UserRecord:
    now = datetime.now(UTC)
    return UserRecord(user_id, "Ada", email, now, now, account_type)


async def seed_organization(
    store: SQLAlchemyStore, *, owner_user_id: str = "owner-1", organization_id: str = "org-1"
) -> str:
    async with store.sessions().begin() as session:
        session.add(
            User(
                id=owner_user_id,
                name="Owner",
                email=f"{owner_user_id}@company.com",
                account_type="employer",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        session.add(Organization(id=organization_id, name="Company"))
        await session.flush()
        session.add(
            OrganizationMember(
                id=f"member-{organization_id}",
                organization_id=organization_id,
                user_id=owner_user_id,
                role="owner",
            )
        )
    return organization_id


async def add_recruiter(store: SQLAlchemyStore, organization_id: str, user_id: str) -> None:
    async with store.sessions().begin() as session:
        session.add(
            User(
                id=user_id,
                name="Recruiter",
                email=f"{user_id}@company.com",
                account_type="employer",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )
        await session.flush()
        session.add(
            OrganizationMember(
                id=f"member-{user_id}",
                organization_id=organization_id,
                user_id=user_id,
                role="recruiter",
            )
        )


async def add_user(store: SQLAlchemyStore, user_id: str, email: str) -> None:
    async with store.sessions().begin() as session:
        session.add(
            User(
                id=user_id,
                name="Outsider",
                email=email,
                account_type="employer",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )
        )


@asynccontextmanager
async def policy_client() -> AsyncGenerator[tuple[AsyncClient, SQLAlchemyStore]]:
    engine = create_async_engine(
        "sqlite+aiosqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as connection:
        await connection.run_sync(
            lambda sync_connection: Base.metadata.create_all(
                # SQLAlchemy types __table__ as FromClause although create_all
                # receives concrete Table instances here.
                sync_connection,
                tables=cast("Sequence[Table]", POLICY_TABLES),
            )
        )
    store = SQLAlchemyStore(engine)
    transport = ASGITransport(app=create_app(store, SETTINGS))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client, store
    await engine.dispose()


def auth_headers(store: SQLAlchemyStore, user: UserRecord) -> dict[str, str]:
    token = AuthService(store, SECRET, timedelta(hours=1)).issue_token(user).token
    return {"Authorization": f"Bearer {token}"}


async def memberships(
    store: SQLAlchemyStore, user_id: str | None = None
) -> list[JoinedOrganization]:
    async with store.sessions()() as session:
        query = select(OrganizationMember.organization_id, OrganizationMember.role)
        if user_id is not None:
            query = query.where(OrganizationMember.user_id == user_id)
        rows = await session.execute(query)
        return [JoinedOrganization(org, "", role) for org, role in rows]


async def test_owner_reads_the_default_join_policy() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        response = await client.get(
            "/api/organizations/org-1/join-policy",
            headers=auth_headers(store, make_user("owner-1", "owner-1@company.com")),
        )

    assert response.status_code == 200
    assert response.json() == {"defaultRole": "viewer", "domains": [], "emails": []}


async def test_owner_updates_the_default_member_role() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        headers_dict = auth_headers(store, make_user("owner-1", "owner-1@company.com"))
        response = await client.put(
            "/api/organizations/org-1/join-policy",
            json={"default_role": "recruiter"},
            headers=headers_dict,
        )

        assert response.status_code == 200
        assert response.json() == {"defaultRole": "recruiter"}

        rejected = await client.put(
            "/api/organizations/org-1/join-policy",
            json={"default_role": "owner"},
            headers=headers_dict,
        )

    assert rejected.status_code == 400


async def test_owner_adds_and_removes_a_domain_rule() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        owner = make_user("owner-1", "owner-1@company.com")
        headers_dict = auth_headers(store, owner)

        added = await client.post(
            "/api/organizations/org-1/join-policy/domains",
            json={"domain": "@Company.COM"},
            headers=headers_dict,
        )
        assert added.status_code == 201
        assert added.json() == {"domain": "company.com"}

        listed = await client.get(
            "/api/organizations/org-1/join-policy", headers=headers_dict
        )
        assert listed.json()["domains"] == ["company.com"]

        removed = await client.delete(
            "/api/organizations/org-1/join-policy/domains/company.com",
            headers=headers_dict,
        )
        assert removed.status_code == 204

        missing = await client.delete(
            "/api/organizations/org-1/join-policy/domains/company.com",
            headers=headers_dict,
        )

    assert missing.status_code == 404


async def test_domain_rule_rejects_public_providers() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        response = await client.post(
            "/api/organizations/org-1/join-policy/domains",
            json={"domain": "gmail.com"},
            headers=auth_headers(store, make_user("owner-1", "owner-1@company.com")),
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


async def test_a_domain_can_only_be_claimed_once() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        await seed_organization(
            store, owner_user_id="owner-2", organization_id="org-2"
        )
        first = await client.post(
            "/api/organizations/org-1/join-policy/domains",
            json={"domain": "company.com"},
            headers=auth_headers(store, make_user("owner-1", "owner-1@company.com")),
        )
        second = await client.post(
            "/api/organizations/org-2/join-policy/domains",
            json={"domain": "company.com"},
            headers=auth_headers(store, make_user("owner-2", "owner-2@company.com")),
        )
        duplicate = await client.post(
            "/api/organizations/org-1/join-policy/domains",
            json={"domain": "company.com"},
            headers=auth_headers(store, make_user("owner-1", "owner-1@company.com")),
        )

    assert first.status_code == 201
    assert second.status_code == 409
    assert duplicate.status_code == 409


async def test_owner_adds_and_removes_an_allowed_email() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        owner = make_user("owner-1", "owner-1@company.com")
        headers_dict = auth_headers(store, owner)

        invalid = await client.post(
            "/api/organizations/org-1/join-policy/emails",
            json={"email": "not-an-email"},
            headers=headers_dict,
        )
        assert invalid.status_code == 400

        added = await client.post(
            "/api/organizations/org-1/join-policy/emails",
            json={"email": "Ada@Personal.org"},
            headers=headers_dict,
        )
        assert added.status_code == 201
        assert added.json() == {"email": "ada@personal.org"}

        duplicate = await client.post(
            "/api/organizations/org-1/join-policy/emails",
            json={"email": "ada@personal.org"},
            headers=headers_dict,
        )
        assert duplicate.status_code == 409

        removed = await client.delete(
            "/api/organizations/org-1/join-policy/emails/ada@personal.org",
            headers=headers_dict,
        )

    assert removed.status_code == 204


async def test_non_owners_cannot_manage_the_join_policy() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        await add_recruiter(store, "org-1", "recruiter-1")
        await add_user(store, "outsider", "outsider@other.com")
        recruiter_headers = auth_headers(store, make_user("recruiter-1", "recruiter-1@company.com"))
        outsider_headers = auth_headers(store, make_user("outsider", "outsider@other.com"))

        responses = [
            await client.get("/api/organizations/org-1/join-policy", headers=recruiter_headers),
            await client.put(
                "/api/organizations/org-1/join-policy",
                json={"default_role": "viewer"},
                headers=recruiter_headers,
            ),
            await client.post(
                "/api/organizations/org-1/join-policy/domains",
                json={"domain": "company.com"},
                headers=recruiter_headers,
            ),
            await client.get("/api/organizations/org-1/join-policy", headers=outsider_headers),
        ]

    statuses = [response.status_code for response in responses]
    assert statuses == [404, 404, 404, 404]


async def test_signup_auto_joins_through_a_claimed_domain_in_a_real_store() -> None:
    async with policy_client() as (client, store):
        await seed_organization(store)
        async with store.sessions().begin() as session:
            session.add(
                OrganizationEmailDomain(id="rule-1", organization_id="org-1", domain="company.com")
            )
        response = await client.post(
            "/api/employer/auth/sign-up/email",
            json={"name": "Ada", "email": "ada@company.com", "password": "password123"},
        )
        user_id = response.json()["user"]["id"]
        joined = await memberships(store, user_id)

    assert response.status_code == 201
    assert joined == [JoinedOrganization("org-1", "", "viewer")]
