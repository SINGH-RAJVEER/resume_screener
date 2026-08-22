
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta

import bcrypt
import pytest
from httpx import ASGITransport, AsyncClient

from app.auth import AuthService
from app.core.config import Settings
from app.main import create_app
from app.persistence.store import EmailAlreadyUsedError, NotFoundError, Store, UserRecord

SECRET = "test-secret-that-is-at-least-32-characters"
SETTINGS = Settings(
    database_url="postgresql://unused/resume_screener",
    web_url="http://localhost:3000",
    jwt_secret=SECRET,
    jwt_ttl=timedelta(days=1),
)
SIGN_UP_BODY = {"name": "Ada", "email": "ada@example.com", "password": "password123"}

pytestmark = pytest.mark.asyncio


class FakeStore:
    def __init__(self, user: UserRecord | None = None, password_hash: str = "") -> None:
        self.user_record = user
        self.password_hash = password_hash
        self.register_error: Exception | None = None
        self.credentials_error: Exception | None = None
        self.user_error: Exception | None = None

    async def register(
        self, name: str, email: str, password_hash: str, account_type: str = "candidate"
    ) -> UserRecord:
        if self.register_error is not None:
            raise self.register_error
        self.password_hash = password_hash
        self.user_record = make_user(name=name, email=email, account_type=account_type)
        return self.user_record

    async def credentials(self, email: str) -> tuple[UserRecord, str]:
        if self.credentials_error is not None:
            raise self.credentials_error
        if self.user_record is None or self.user_record.email != email:
            raise NotFoundError
        return self.user_record, self.password_hash

    async def user(self, user_id: str) -> UserRecord:
        if self.user_error is not None:
            raise self.user_error
        if self.user_record is None or self.user_record.id != user_id:
            raise NotFoundError
        return self.user_record


def make_user(
    name: str = "Ada", email: str = "ada@example.com", account_type: str = "candidate"
) -> UserRecord:
    now = datetime.now(UTC)
    return UserRecord("user-1", name, email, now, now, account_type)


def token_for(store: Store, user: UserRecord, ttl: timedelta = timedelta(hours=1)) -> str:
    return AuthService(store, SECRET, ttl).issue_token(user).token


@asynccontextmanager
async def api_client(
    store: Store,
    *,
    raise_app_exceptions: bool = True,
) -> AsyncGenerator[AsyncClient]:
    transport = ASGITransport(
        app=create_app(store, SETTINGS),
        raise_app_exceptions=raise_app_exceptions,
    )
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def test_health() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_app_requires_complete_test_dependencies() -> None:
    with pytest.raises(ValueError, match="store and settings must be provided together"):
        create_app(store=FakeStore())


async def test_signup_normalizes_email_hashes_password_and_returns_jwt() -> None:
    store = FakeStore()
    async with api_client(store) as client:
        response = await client.post(
            "/api/auth/sign-up/email",
            json={**SIGN_UP_BODY, "email": "ADA@example.com"},
        )

    assert response.status_code == 201
    assert store.user_record is not None
    assert store.user_record.email == "ada@example.com"
    assert bcrypt.checkpw(b"password123", store.password_hash.encode())
    assert response.json()["tokenType"] == "Bearer"
    authenticated = await AuthService(store, SECRET, timedelta(hours=1)).authenticate(
        response.json()["token"]
    )
    assert authenticated.id == "user-1"


async def test_employer_signup_creates_an_employer_account() -> None:
    store = FakeStore()
    async with api_client(store) as client:
        response = await client.post(
            "/api/employer/auth/sign-up/email",
            json=SIGN_UP_BODY,
        )

    assert response.status_code == 201
    assert response.json()["user"]["accountType"] == "employer"


async def test_candidate_signin_rejects_an_employer_account() -> None:
    store = FakeStore(make_user(account_type="employer"))
    store.password_hash = bcrypt.hashpw(b"password123", bcrypt.gensalt()).decode()
    async with api_client(store) as client:
        response = await client.post(
            "/api/auth/sign-in/email",
            json={"email": "ada@example.com", "password": "password123"},
        )

    assert response.status_code == 401


async def test_signup_rejects_trailing_json() -> None:
    body = b'{"name":"Ada","email":"ada@example.com","password":"password123"} {}'
    async with api_client(FakeStore()) as client:
        response = await client.post("/api/auth/sign-up/email", content=body)

    assert response.status_code == 400
    assert response.json() == {"code": "INVALID_REQUEST", "message": "invalid JSON body"}


async def test_signup_rejects_unknown_fields() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.post(
            "/api/auth/sign-up/email",
            json={**SIGN_UP_BODY, "extra": True},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


async def test_signup_validates_credentials() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.post(
            "/api/auth/sign-up/email",
            json={"name": "", "email": "bad", "password": "short"},
        )

    assert response.status_code == 400
    assert response.json() == {
        "code": "INVALID_CREDENTIALS",
        "message": "Name must be between 1 and 100 characters",
    }


async def test_signin_rejects_invalid_password() -> None:
    password_hash = bcrypt.hashpw(b"correct-password", bcrypt.gensalt()).decode()
    store = FakeStore(make_user(), password_hash)
    async with api_client(store) as client:
        response = await client.post(
            "/api/auth/sign-in/email",
            json={"email": "ada@example.com", "password": "wrong-password"},
        )

    assert response.status_code == 401
    assert response.json() == {
        "code": "INVALID_EMAIL_OR_PASSWORD",
        "message": "Invalid email or password",
    }


async def test_signin_rejects_passwords_over_the_bcrypt_limit() -> None:
    store = FakeStore(make_user(), bcrypt.hashpw(b"correct-password", bcrypt.gensalt()).decode())
    async with api_client(store) as client:
        response = await client.post(
            "/api/auth/sign-in/email",
            json={"email": "ada@example.com", "password": "a" * 73},
        )

    assert response.status_code == 401


async def test_signin_reports_store_failures_as_internal_errors() -> None:
    store = FakeStore()
    store.credentials_error = RuntimeError("database unavailable")
    async with api_client(store, raise_app_exceptions=False) as client:
        response = await client.post(
            "/api/auth/sign-in/email",
            json={"email": "ada@example.com", "password": "password123"},
        )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


async def test_me_requires_a_bearer_token() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.get("/api/me")

    assert response.status_code == 401


async def test_me_returns_the_authenticated_user() -> None:
    account = make_user()
    store = FakeStore(account)
    token = token_for(store, account)
    async with api_client(store) as client:
        response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-1"


async def test_session_returns_null_without_a_valid_token() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.get("/api/auth/session")

    assert response.status_code == 200
    assert response.json() is None


async def test_session_returns_the_authenticated_user() -> None:
    account = make_user()
    store = FakeStore(account)
    token = token_for(store, account)
    async with api_client(store) as client:
        response = await client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 200
    assert response.json()["user"]["id"] == "user-1"


async def test_session_reports_store_failures_as_internal_errors() -> None:
    account = make_user()
    store = FakeStore(account)
    store.user_error = RuntimeError("database unavailable")
    token = token_for(store, account)
    async with api_client(store, raise_app_exceptions=False) as client:
        response = await client.get(
            "/api/auth/session",
            headers={"Authorization": f"Bearer {token}"},
        )

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"


async def test_expired_jwt_is_unauthorized() -> None:
    account = make_user()
    store = FakeStore(account)
    token = token_for(store, account, timedelta(hours=-1))
    async with api_client(store) as client:
        response = await client.get("/api/me", headers={"Authorization": f"Bearer {token}"})

    assert response.status_code == 401


async def test_signout_succeeds() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.post("/api/auth/sign-out")

    assert response.status_code == 200
    assert response.json() == {"success": True}


async def test_cors_allows_the_web_origin() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.options(
            "/api/auth/session",
            headers={"Origin": "http://localhost:3000"},
        )

    assert response.status_code == 204
    assert "Authorization" in response.headers["access-control-allow-headers"]


async def test_cors_rejects_other_origins() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.get("/health", headers={"Origin": "https://attacker.example"})

    assert response.status_code == 403
    assert response.json() == {"code": "ORIGIN_NOT_ALLOWED", "message": "Origin is not allowed"}


async def test_signup_rejects_an_existing_email() -> None:
    store = FakeStore()
    store.register_error = EmailAlreadyUsedError()
    async with api_client(store) as client:
        response = await client.post("/api/auth/sign-up/email", json=SIGN_UP_BODY)

    assert response.status_code == 409


async def test_request_body_is_limited_to_one_mib() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.post(
            "/api/auth/sign-up/email",
            content=b"{" + b"a" * (1 << 20) + b"}",
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"


async def test_application_window_accepts_iso_timestamp_strings() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.put(
            "/api/jobs/job-1/application-window",
            json={
                "opens_at": "2026-08-01T09:00:00+00:00",
                "closes_at": "2026-08-08T17:00:00+00:00",
            },
        )

    assert response.status_code == 401


async def test_application_window_rejects_non_timestamp_values() -> None:
    async with api_client(FakeStore()) as client:
        response = await client.put(
            "/api/jobs/job-1/application-window",
            json={"opens_at": 123, "closes_at": "2026-08-08T17:00:00+00:00"},
        )

    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_REQUEST"
