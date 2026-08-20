from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from datetime import timedelta

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .auth import AuthService, InvalidCredentialsError, ValidationError, user_json
from .config import Settings, load_settings
from .http import (
    APIError,
    BodyLimitMiddleware,
    CORSMiddleware,
    InvalidRequestError,
    RecoveryMiddleware,
    RequestLoggingMiddleware,
    SignInRequest,
    SignUpRequest,
    decode_json,
    error_body,
)
from .store import EmailAlreadyUsedError, SQLAlchemyStore, Store, create_engine_for_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(application: FastAPI):
    if not hasattr(application.state, "store"):
        settings = load_settings()
        application.state.settings = settings
        engine = create_engine_for_url(settings.database_url)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        application.state.engine = engine
        application.state.store = SQLAlchemyStore(engine)
    yield
    engine = getattr(application.state, "engine", None)
    if engine is not None:
        await engine.dispose()


def create_app(store: Store | None = None, settings: Settings | None = None) -> FastAPI:
    application = FastAPI(lifespan=lifespan)
    if store is not None:
        application.state.store = store
    if settings is None:
        settings = Settings(
            database_url="",
            port=8000,
            web_url=os.environ.get("WEB_URL", "") or "http://localhost:3000",
            jwt_secret="",
            jwt_ttl=timedelta(days=7),
        )
    application.state.settings = settings

    @application.exception_handler(APIError)
    async def api_error_handler(_request: Request, error: APIError) -> JSONResponse:
        return JSONResponse(error_body(error.code, error.message), status_code=error.status)

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, error: Exception) -> JSONResponse:
        logging.getLogger("template-api").exception("unhandled request error", exc_info=error)
        return JSONResponse(error_body("INTERNAL_ERROR", "Internal server error"), status_code=500)

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/auth/sign-up/email")
    async def sign_up(request: Request) -> JSONResponse:
        try:
            input_data = await decode_json(request, SignUpRequest)
        except InvalidRequestError:
            raise APIError(400, "INVALID_REQUEST", "invalid JSON body") from None
        service = auth_service(request)
        try:
            result = await service.register(input_data.name, input_data.email, input_data.password)
        except ValidationError as error:
            raise APIError(400, "INVALID_CREDENTIALS", str(error)) from error
        except EmailAlreadyUsedError:
            raise APIError(409, "EMAIL_ALREADY_EXISTS", "Email is already registered") from None
        except Exception:
            logging.getLogger("template-api").exception("register user")
            raise APIError(500, "INTERNAL_ERROR", "Could not create account") from None
        return JSONResponse(jsonable_encoder(result), status_code=201)

    @application.post("/api/auth/sign-in/email")
    async def sign_in(request: Request) -> JSONResponse:
        try:
            input_data = await decode_json(request, SignInRequest)
        except InvalidRequestError:
            raise APIError(400, "INVALID_REQUEST", "invalid JSON body") from None
        try:
            result = await auth_service(request).sign_in(input_data.email, input_data.password)
        except InvalidCredentialsError:
            raise APIError(401, "INVALID_EMAIL_OR_PASSWORD", "Invalid email or password") from None
        except Exception:
            logging.getLogger("template-api").exception("sign in")
            raise APIError(500, "INTERNAL_ERROR", "Could not sign in") from None
        return JSONResponse(jsonable_encoder(result))

    @application.post("/api/auth/sign-out")
    async def sign_out() -> dict[str, bool]:
        return {"success": True}

    @application.get("/api/auth/session")
    async def session(request: Request) -> JSONResponse:
        user = await authenticated_user(request)
        return JSONResponse(jsonable_encoder(None if user is None else {"user": user_json(user)}))

    @application.get("/api/me")
    async def me(request: Request) -> JSONResponse:
        user = await authenticated_user(request)
        if user is None:
            raise APIError(401, "UNAUTHORIZED", "Unauthorized")
        return JSONResponse(jsonable_encoder({"user": user_json(user)}))

    application.add_middleware(BodyLimitMiddleware)
    application.add_middleware(CORSMiddleware, web_url=settings.web_url)
    application.add_middleware(RecoveryMiddleware)
    application.add_middleware(RequestLoggingMiddleware)
    return application


def auth_service(request: Request) -> AuthService:
    settings: Settings = request.app.state.settings
    store: Store = request.app.state.store
    return AuthService(store, settings.jwt_secret, settings.jwt_ttl)


async def authenticated_user(request: Request):
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.casefold() != "bearer" or not token:
        return None
    try:
        return await auth_service(request).authenticate(token)
    except InvalidCredentialsError:
        return None
    except Exception:
        logging.getLogger("template-api").debug("reject bearer token", exc_info=True)
        return None


app = create_app()
