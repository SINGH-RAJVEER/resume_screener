
import json
import logging
from time import perf_counter

from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("resume-screener.api")
MAX_BODY_BYTES = 1 << 20
MAX_MULTIPART_BODY_BYTES = 20 << 20


class _RequestBodyTooLargeError(Exception):
    pass


class APIError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        self.status = status
        self.code = code
        self.message = message


def error_body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        content_type = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-type"),
            b"",
        )
        limit = (
            MAX_MULTIPART_BODY_BYTES
            if b"multipart/form-data" in content_type
            else MAX_BODY_BYTES
        )
        content_length = next(
            (value for key, value in scope.get("headers", []) if key.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > limit:
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
                if consumed > limit:
                    raise _RequestBodyTooLargeError
            return message

        try:
            await self.app(scope, limited_receive, send)
        except _RequestBodyTooLargeError:
            await send_error(send, 400, "INVALID_REQUEST", "invalid JSON body")


class OriginGuardMiddleware:
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

        started = perf_counter()
        try:
            await self.app(scope, receive, tracked_send)
        except Exception:
            status = 500
            raise
        finally:
            logger.info(
                "%s %s %d %.3fs",
                scope.get("method", ""),
                scope.get("path", ""),
                status,
                perf_counter() - started,
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
