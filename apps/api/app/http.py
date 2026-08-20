from __future__ import annotations

import json
import logging

from fastapi import Request
from pydantic import BaseModel, ConfigDict, ValidationError
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("template-api")
MAX_BODY_BYTES = 1 << 20


class InvalidRequestError(Exception):
    pass


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


async def decode_json[ModelT: BaseModel](request: Request, model: type[ModelT]) -> ModelT:
    try:
        body = await request.body()
        value = json.loads(body, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        if not isinstance(value, dict):
            raise ValueError
        return model.model_validate(value)
    except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as error:
        raise InvalidRequestError from error


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > MAX_BODY_BYTES:
                    await send_error(send, 400, "INVALID_REQUEST", "invalid JSON body")
                    return
            except ValueError:
                pass

        consumed = 0

        async def limited_receive() -> Message:
            nonlocal consumed
            message = await receive()
            if message["type"] == "http.request":
                consumed += len(message.get("body", b""))
                if consumed > MAX_BODY_BYTES:
                    raise InvalidRequestError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except InvalidRequestError:
            await send_error(send, 400, "INVALID_REQUEST", "invalid JSON body")


class CORSMiddleware:
    def __init__(self, app: ASGIApp, web_url: str) -> None:
        self.app = app
        self.web_url = web_url.rstrip("/")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        origin = headers.get(b"origin", b"").decode().rstrip("/")
        if origin and origin != self.web_url:
            await send_error(send, 403, "ORIGIN_NOT_ALLOWED", "Origin is not allowed")
            return

        async def cors_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_headers = list(message.get("headers", []))
                if origin:
                    response_headers.extend(
                        [(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin")]
                    )
                message = {**message, "headers": response_headers}
            await send(message)

        if scope.get("method") == "OPTIONS":
            options_headers = [
                (b"access-control-allow-headers", b"Content-Type, Authorization"),
                (b"access-control-allow-methods", b"GET, POST, PUT, DELETE, OPTIONS"),
                (b"access-control-max-age", b"600"),
            ]
            if origin:
                options_headers.extend(
                    [(b"access-control-allow-origin", origin.encode()), (b"vary", b"Origin")]
                )
            await send({"type": "http.response.start", "status": 204, "headers": options_headers})
            await send({"type": "http.response.body", "body": b""})
            return
        await self.app(scope, receive, cors_send)


class RecoveryMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        response_started = False

        async def tracked_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            logger.exception("error serving request", extra={"path": scope.get("path", "")})
            if not response_started:
                await send_error(send, 500, "INTERNAL_ERROR", "Internal server error")


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        status = 200

        async def tracked_send(message: Message) -> None:
            nonlocal status
            if message["type"] == "http.response.start":
                status = int(message["status"])
            await send(message)

        started = __import__("time").perf_counter()
        try:
            await self.app(scope, receive, tracked_send)
        finally:
            logger.info(
                "request",
                extra={
                    "method": scope.get("method", ""),
                    "path": scope.get("path", ""),
                    "status": status,
                    "duration": __import__("time").perf_counter() - started,
                },
            )


async def send_error(send: Send, status: int, code: str, message: str) -> None:
    body = json.dumps(error_body(code, message), separators=(",", ":")).encode()
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [(b"content-type", b"application/json; charset=utf-8")],
        }
    )
    await send({"type": "http.response.body", "body": body})


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class SignUpRequest(RequestModel):
    name: str = ""
    email: str = ""
    password: str = ""
    callbackURL: str = ""


class SignInRequest(RequestModel):
    email: str = ""
    password: str = ""
    callbackURL: str = ""
