from __future__ import annotations

import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .config import Settings, load_settings
from .http import (
    APIError,
    BodySizeLimitMiddleware,
    OriginGuardMiddleware,
    RequestLoggingMiddleware,
    error_body,
)
from .routes import router
from .store import SQLAlchemyStore, Store, create_engine_for_url

logger = logging.getLogger("resume-screener.api")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    engine = None
    if application.state.store is None:
        settings = application.state.settings or load_settings()
        application.state.settings = settings
        engine = create_engine_for_url(settings.database_url)
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
        application.state.store = SQLAlchemyStore(engine)
    try:
        yield
    finally:
        if engine is not None:
            await engine.dispose()


def create_app(store: Store | None = None, settings: Settings | None = None) -> FastAPI:
    application = FastAPI(lifespan=lifespan)
    application.state.store = store
    application.state.settings = settings
    web_url = settings.web_url if settings else os.environ.get("WEB_URL") or "http://localhost:3000"

    @application.exception_handler(APIError)
    async def api_error_handler(_request: Request, error: APIError) -> JSONResponse:
        return JSONResponse(error_body(error.code, error.message), status_code=error.status)

    @application.exception_handler(RequestValidationError)
    async def invalid_request_handler(
        _request: Request,
        _error: RequestValidationError,
    ) -> JSONResponse:
        return JSONResponse(error_body("INVALID_REQUEST", "invalid JSON body"), status_code=400)

    @application.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, error: Exception) -> JSONResponse:
        logger.exception("unhandled request error", exc_info=error)
        return JSONResponse(error_body("INTERNAL_ERROR", "Internal server error"), status_code=500)

    application.include_router(router)
    application.add_middleware(BodySizeLimitMiddleware)
    application.add_middleware(OriginGuardMiddleware, web_url=web_url)
    application.add_middleware(RequestLoggingMiddleware)
    return application


app = create_app()
