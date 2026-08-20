from __future__ import annotations

from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import AuthService
from app.config import Settings
from app.main import create_app
from app.store import EmailAlreadyUsedError, NotFoundError, UserRecord

SECRET = "test-secret-that-is-at-least-32-characters"
SETTINGS = Settings(
    database_url="postgresql://unused/template",
    web_url="http://localhost:3000",
    jwt_secret=SECRET,
    jwt_ttl=timedelta(days=1),
)
ClientFactory = Callable[["FakeStore"], Awaitable[AsyncClient]]


class FakeStore:
    def __init__(self, user: UserRecord | None = None, password_hash: str = "") -> None:
        self.user_record = user
        self.password_hash = password_hash
        self.register_error: Exception | None = None

    async def register(self, name: str, email: str, password_hash: str) -> UserRecord:
        if self.register_error is not None:
            raise self.register_error
        now = datetime.now(UTC)
        self.password_hash = password_hash
        self.user_record = UserRecord("user-1", name, email, now, now)
        return self.user_record
    async def credentials(self, email: str) -> tuple[UserRecord, str]:
        if self.user_record is None or self.user_record.email != email:
            raise NotFoundError
        return self.user_record, self.password_hash

    async def user(self, user_id: str) -> UserRecord:
        if self.user_record is None or self.user_record.id != user_id:
            raise NotFoundError
        return self.user_record


def user(name: str = "Ada", email: str = "ada@example.com") -> UserRecord:
    now = datetime.now(UTC)
    return UserRecord("user-1", name, email, now, now)


@pytest.fixture
def client() -> ClientFactory:
    async def make_client(store: FakeStore) -> AsyncClient:
        return AsyncClient(
            transport=ASGITransport(app=create_app(store, SETTINGS)), base_url="http://test"
        )

    return make_client


@pytest.mark.asyncio
async def test_health(client: ClientFactory) -> None:
    async with await client(FakeStore()) as http:
        response = await http.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_signup_normalizes_email_hashes_password_and_returns_jwt(
    client: ClientFactory,
) -> None:
    store = FakeStore(user(name="", email=""))
    async with await client(store) as http:
        response = await http.post(
            "/api/auth/sign-up/email",
            json={"name": "Ada", "email": "ADA@example.com", "password": "password123"},
        )
    assert response.status_code == 201
    assert store.user_record is not None
    assert store.user_record.email == "ada@example.com"
    assert bcrypt.checkpw(b"password123", store.password_hash.encode())
    assert response.json()["tokenType"] == "Bearer"
    claims = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
        response.json()["token"], SECRET, algorithms=["HS256"], issuer="template-api"
    )
    assert claims["sub"] == "user-1"


@pytest.mark.asyncio
async def test_signup_rejects_trailing_json_and_unknown_fields(client: ClientFactory) -> None:
    async with await client(FakeStore()) as http:
        trailing = await http.post(
            "/api/auth/sign-up/email",
            content=b'{"name":"Ada","email":"ada@example.com","password":"password123"} {}',
        )
        unknown = await http.post(
            "/api/auth/sign-up/email",
            json={"name": "Ada", "email": "ada@example.com", "password": "password123", "extra": 1},
        )
    assert trailing.status_code == 400
    assert trailing.json() == {"code": "INVALID_REQUEST", "message": "invalid JSON body"}
    assert unknown.status_code == 400
    assert unknown.json()["code"] == "INVALID_REQUEST"


@pytest.mark.asyncio
async def test_signup_validation(client: ClientFactory) -> None:
    async with await client(FakeStore()) as http:
        response = await http.post(
            "/api/auth/sign-up/email", json={"name": "", "email": "bad", "password": "short"}
        )
    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_CREDENTIALS",
        "message": "Name must be between 1 and 100 characters",
    }


@pytest.mark.asyncio
async def test_signin_rejects_invalid_password(client: ClientFactory) -> None:
    account = user()
    store = FakeStore(account, bcrypt.hashpw(b"correct-password", bcrypt.gensalt()).decode())
    async with await client(store) as http:
        response = await http.post(
            "/api/auth/sign-in/email",
            json={"email": "ada@example.com", "password": "wrong-password"},
        )
    assert response.status_code == 401
    assert response.json() == {
        "code": "INVALID_EMAIL_OR_PASSWORD",
        "message": "Invalid email or password",
    }


@pytest.mark.asyncio
async def test_me_and_session_require_valid_jwt(client: ClientFactory) -> None:
    account = user()
    store = FakeStore(account)
    token = AuthService(store, SECRET, timedelta(hours=1)).issue_token(account).token
    async with await client(store) as http:
        unauthorized = await http.get("/api/me")
        authorized = await http.get("/api/me", headers={"Authorization": f"Bearer {token}"})
        session = await http.get("/api/auth/session", headers={"Authorization": f"Bearer {token}"})
    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    assert authorized.json()["user"]["id"] == "user-1"
    assert session.json()["user"]["id"] == "user-1"


@pytest.mark.asyncio
async def test_expired_jwt_is_unauthorized(client: ClientFactory) -> None:
    account = user()
    store = FakeStore(account)
    token = AuthService(store, SECRET, timedelta(hours=-1)).issue_token(account).token
    async with await client(store) as http:
        response = await http.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_signout_is_stateless_and_cors_matches_go_behavior(client: ClientFactory) -> None:
    store = FakeStore()
    async with await client(store) as http:
        signout = await http.post("/api/auth/sign-out")
        preflight = await http.options(
            "/api/auth/session", headers={"Origin": "http://localhost:3000"}
        )
        blocked = await http.get("/health", headers={"Origin": "https://attacker.example"})
    assert signout.status_code == 200
    assert signout.json() == {"success": True}
    assert preflight.status_code == 204
    assert "Authorization" in preflight.headers["access-control-allow-headers"]
    assert blocked.status_code == 403
    assert blocked.json() == {"code": "ORIGIN_NOT_ALLOWED", "message": "Origin is not allowed"}


@pytest.mark.asyncio
async def test_signup_email_conflict(client: ClientFactory) -> None:
    store = FakeStore()
    store.register_error = EmailAlreadyUsedError()
    async with await client(store) as http:
        response = await http.post(
            "/api/auth/sign-up/email",
            json={"name": "Ada", "email": "ada@example.com", "password": "password123"},
        )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_request_body_is_limited_to_one_mib(client: ClientFactory) -> None:
    async with await client(FakeStore()) as http:
        response = await http.post(
            "/api/auth/sign-up/email", content=b"{" + b"a" * (1 << 20) + b"}"
        )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
