
import re
from asyncio import to_thread
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parseaddr

import bcrypt
import jwt

from .persistence.store import NotFoundError, Store, UserRecord

JWT_ISSUER = "skillsignal-api"


class InvalidCredentialsError(Exception):
    pass


class CredentialValidationError(Exception):
    pass


@dataclass(frozen=True)
class AuthResult:
    user: UserRecord
    token: str
    expires_at: datetime


def validate_email(email: str) -> None:
    parsed_name, parsed_email = parseaddr(email)
    _, _, domain = parsed_email.rpartition("@")
    if (
        not parsed_email
        or parsed_name
        or parsed_email.casefold() != email.casefold()
        or not domain or "." not in domain
        or len(email.encode()) > 254
        or re.search(r"\s", email)
    ):
        raise CredentialValidationError("Enter a valid email address")


def validate_credentials(name: str, email: str, password: str) -> None:
    if not name or len(name.encode()) > 100:
        raise CredentialValidationError("Name must be between 1 and 100 characters")
    validate_email(email)
    password_length = len(password.encode())
    if password_length < 8 or password_length > 72:
        raise CredentialValidationError("Password must be between 8 and 72 characters")


class AuthService:
    def __init__(self, store: Store, jwt_secret: str, jwt_ttl: timedelta) -> None:
        self._store = store
        self._jwt_secret = jwt_secret
        self._jwt_ttl = jwt_ttl

    async def register(
        self, name: str, email: str, password: str, account_type: str = "candidate"
    ) -> AuthResult:
        name = name.strip()
        email = email.strip().lower()
        validate_credentials(name, email, password)
        password_hash = await to_thread(hash_password, password)
        user = await self._store.register(name, email, password_hash, account_type)
        return self.issue_token(user)

    async def sign_in(
        self, email: str, password: str, expected_account_type: str | None = None
    ) -> AuthResult:
        email = email.strip().lower()
        try:
            user, password_hash = await self._store.credentials(email)
        except NotFoundError:
            raise InvalidCredentialsError from None
        if len(password.encode()) > 72 or not await to_thread(
            check_password, password, password_hash
        ):
            raise InvalidCredentialsError
        if expected_account_type is not None and user.account_type != expected_account_type:
            raise InvalidCredentialsError
        return self.issue_token(user)

    def issue_token(self, user: UserRecord) -> AuthResult:
        now = datetime.now(UTC)
        expires_at = now + self._jwt_ttl
        claims = {
            "iss": JWT_ISSUER,
            "sub": user.id,
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        token = jwt.encode(  # pyright: ignore[reportUnknownMemberType]
            claims, self._jwt_secret, algorithm="HS256"
        )
        return AuthResult(user=user, token=token, expires_at=expires_at)

    async def authenticate(self, token: str) -> UserRecord:
        try:
            claims = jwt.decode(  # pyright: ignore[reportUnknownMemberType]
                token,
                self._jwt_secret,
                algorithms=["HS256"],
                issuer=JWT_ISSUER,
                options={"require": ["exp", "sub"]},
            )
            subject = claims.get("sub")
            if not isinstance(subject, str) or not subject:
                raise InvalidCredentialsError
            return await self._store.user(subject)
        except (jwt.InvalidTokenError, NotFoundError, InvalidCredentialsError):
            raise InvalidCredentialsError from None


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()


def check_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), password_hash.encode())
    except ValueError:
        return False
