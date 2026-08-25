from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import AuthService
from app.core.config import Settings
from app.main import create_app
from app.persistence.store import (
    JoinedOrganization,
    NotFoundError,
    Store,
    UserRecord,
)

SECRET = "test-secret-that-is-at-least-32-characters"
SETTINGS = Settings(
    database_url="postgresql://unused/skillsignal",
    web_url="http://localhost:3000",
    jwt_secret=SECRET,
    jwt_ttl=timedelta(days=1),
)

pytestmark = pytest.mark.asyncio


class SingleUserStore:
    """Serves one fixed user record so guardrails can be exercised."""

    def __init__(self, user: UserRecord) -> None:
        self.user_record = user

    async def register(
        self, name: str, email: str, password_hash: str, account_type: str = "candidate"
    ) -> UserRecord:
        raise NotImplementedError

    async def credentials(self, email: str) -> tuple[UserRecord, str]:
        raise NotFoundError

    async def user(self, user_id: str) -> UserRecord:
        if self.user_record.id != user_id:
            raise NotFoundError
        return self.user_record

    async def apply_join_policies(
        self, user_id: str, email: str
    ) -> list[JoinedOrganization]:
        return []


def make_user(account_type: str, is_demo: bool) -> UserRecord:
    now = datetime.now(UTC)
    return UserRecord(
        id="demo-user-1" if is_demo else "user-1",
        name="Demo",
        email="demo@example.com",
        created_at=now,
        updated_at=now,
        account_type=account_type,
        is_demo=is_demo,
    )


async def client_for(user: UserRecord) -> AsyncClient:
    store: Store = SingleUserStore(user)
    transport = ASGITransport(app=create_app(store, SETTINGS))
    return AsyncClient(transport=transport, base_url="http://test")


def headers_for(store: Store, user: UserRecord) -> dict[str, str]:
    token = AuthService(store, SECRET, timedelta(hours=1)).issue_token(user).token
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.parametrize(
    ("account_type", "method", "path", "body"),
    [
        ("employer", "post", "/api/organizations", {"name": "Org"}),
        (
            "employer",
            "put",
            "/api/jobs/job-1/application-window",
            {
                "opens_at": "2026-09-01T09:00:00Z",
                "closes_at": "2026-09-30T17:00:00Z",
            },
        ),
        ("employer", "post", "/api/billing/orders", {"pack_id": "starter"}),
        ("candidate", "delete", "/api/independent-evaluations/evaluation-1", None),
    ],
)
async def test_demo_accounts_cannot_run_state_changing_commands(
    account_type: str, method: str, path: str, body: dict[str, object] | None
) -> None:
    user = make_user(account_type, is_demo=True)
    client = await client_for(user)
    async with client as authorized:
        response = await authorized.request(
            method,
            path,
            json=body,
            headers=headers_for(SingleUserStore(user), user),
        )

    assert response.status_code == 403
    assert response.json()["code"] == "DEMO_ACCOUNT"


async def test_regular_accounts_are_not_blocked() -> None:
    user = make_user("employer", is_demo=False)
    store: Store = SingleUserStore(user)
    client = await client_for(user)
    async with client as authorized:
        response = await authorized.post(
            "/api/organizations",
            json={"name": "Org"},
            headers=headers_for(store, user),
        )

    # The fake store cannot complete the command, but the demo guard must not
    # be the reason the request fails.
    assert response.status_code != 403
