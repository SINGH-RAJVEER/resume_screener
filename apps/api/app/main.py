
import asyncio
import logging
import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from .api.billing_routes import router as billing_router
from .api.demo_routes import router as demo_router
from .api.routes import router
from .core.config import Settings, load_settings
from .core.http import (
    APIError,
    BodySizeLimitMiddleware,
    OriginGuardMiddleware,
    RequestLoggingMiddleware,
    error_body,
)
from .documents.storage import LocalObjectStorage
from .persistence.retention import purge_expired_data
from .persistence.store import SQLAlchemyStore, Store, create_engine_for_url
from .telemetry import instrument_app, instrument_engine, setup_telemetry

logger = logging.getLogger("skillsignal.api")


async def retention_sweep_loop(engine: AsyncEngine, settings: Settings) -> None:
    """Periodically remove data past its configured retention date."""
    store = SQLAlchemyStore(engine)
    storage = LocalObjectStorage(Path(settings.storage_root))
    while True:
        await asyncio.sleep(settings.retention_sweep_interval_seconds)
        try:
            async with store.sessions().begin() as session:
                await purge_expired_data(session, storage, datetime.now(UTC))
        except Exception:
            logger.exception("retention sweep failed")


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncGenerator[None]:
    engine = None
    sweep_task: asyncio.Task[None] | None = None
    if application.state.store is None:
        settings = application.state.settings or load_settings()
        application.state.settings = settings
        engine = create_engine_for_url(settings.database_url)
        if settings.retention_sweep_interval_seconds > 0:
            sweep_task = asyncio.create_task(retention_sweep_loop(engine, settings))
    try:
        if engine is not None:
            instrument_engine(engine)
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            application.state.store = SQLAlchemyStore(engine)
        yield
    finally:
        if sweep_task is not None:
            sweep_task.cancel()
            await asyncio.gather(sweep_task, return_exceptions=True)
        if engine is not None:
            await engine.dispose()


def create_app(store: Store | None = None, settings: Settings | None = None) -> FastAPI:
    if (store is None) != (settings is None):
        raise ValueError("store and settings must be provided together")
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
    application.include_router(billing_router)
    application.include_router(demo_router)
    application.add_middleware(BodySizeLimitMiddleware)
    application.add_middleware(OriginGuardMiddleware, web_url=web_url)
    application.add_middleware(RequestLoggingMiddleware)
    if setup_telemetry():
        instrument_app(application)
    return application


app = create_app()
