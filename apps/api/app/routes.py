from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from .auth import AuthResult, AuthService, CredentialValidationError, InvalidCredentialsError
from .http import APIError
from .store import EmailAlreadyUsedError, Store, UserRecord


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SignUpRequest(RequestModel):
    name: str = ""
    email: str = ""
    password: str = ""


class SignInRequest(RequestModel):
    email: str = ""
    password: str = ""


class ResponseModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, from_attributes=True, populate_by_name=True)


class UserResponse(ResponseModel):
    id: str
    name: str
    email: str
    email_verified: bool
    image: str | None
    created_at: datetime
    updated_at: datetime


class AuthResponse(ResponseModel):
    user: UserResponse
    token: str
    token_type: str = "Bearer"
    expires_at: datetime


class SessionResponse(ResponseModel):
    user: UserResponse


router = APIRouter()


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/api/auth/sign-up/email", response_model=AuthResponse, status_code=201)
async def sign_up(input_data: SignUpRequest, request: Request) -> AuthResponse:
    try:
        result = await auth_service(request).register(
            input_data.name,
            input_data.email,
            input_data.password,
        )
    except CredentialValidationError as error:
        raise APIError(400, "INVALID_CREDENTIALS", str(error)) from error
    except EmailAlreadyUsedError:
        raise APIError(409, "EMAIL_ALREADY_EXISTS", "Email is already registered") from None
    return auth_response(result)


@router.post("/api/auth/sign-in/email", response_model=AuthResponse)
async def sign_in(input_data: SignInRequest, request: Request) -> AuthResponse:
    try:
        result = await auth_service(request).sign_in(input_data.email, input_data.password)
    except InvalidCredentialsError:
        raise APIError(401, "INVALID_EMAIL_OR_PASSWORD", "Invalid email or password") from None
    return auth_response(result)


@router.post("/api/auth/sign-out")
async def sign_out() -> dict[str, bool]:
    return {"success": True}


@router.get("/api/auth/session", response_model=SessionResponse | None)
async def session(request: Request) -> SessionResponse | None:
    user = await authenticated_user(request)
    return None if user is None else SessionResponse(user=UserResponse.model_validate(user))


@router.get("/api/me", response_model=SessionResponse)
async def me(request: Request) -> SessionResponse:
    user = await authenticated_user(request)
    if user is None:
        raise APIError(401, "UNAUTHORIZED", "Unauthorized")
    return SessionResponse(user=UserResponse.model_validate(user))


def auth_service(request: Request) -> AuthService:
    settings = request.app.state.settings
    store: Store = request.app.state.store
    return AuthService(store, settings.jwt_secret, settings.jwt_ttl)


async def authenticated_user(request: Request) -> UserRecord | None:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        return None
    try:
        return await auth_service(request).authenticate(token)
    except InvalidCredentialsError:
        return None


def auth_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        user=UserResponse.model_validate(result.user),
        token=result.token,
        expires_at=result.expires_at,
    )
