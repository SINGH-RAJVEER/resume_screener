import hashlib
import hmac
from typing import cast

import httpx


class RazorpayError(Exception):
	pass


class RazorpayUnavailableError(RazorpayError):
	pass


def verify_checkout_signature(
	order_id: str, payment_id: str, signature: str, key_secret: str
) -> bool:
	expected = hmac.new(
		key_secret.encode(), f"{order_id}|{payment_id}".encode(), hashlib.sha256
	).hexdigest()
	return hmac.compare_digest(expected, signature)


def verify_webhook_signature(body: bytes, signature: str, webhook_secret: str) -> bool:
	expected = hmac.new(webhook_secret.encode(), body, hashlib.sha256).hexdigest()
	return hmac.compare_digest(expected, signature)


class RazorpayClient:
	def __init__(
		self,
		key_id: str,
		key_secret: str,
		base_url: str = "https://api.razorpay.com/v1",
		timeout_seconds: float = 15.0,
		transport: httpx.AsyncBaseTransport | None = None,
	) -> None:
		if not key_id or not key_secret:
			raise RazorpayUnavailableError("Razorpay credentials are not configured")
		self._auth = (key_id, key_secret)
		self._base_url = base_url.rstrip("/")
		self._timeout_seconds = timeout_seconds
		self._transport = transport

	async def create_order(
		self,
		amount_paise: int,
		currency: str,
		receipt: str,
		notes: dict[str, str] | None = None,
	) -> dict[str, object]:
		body = await self._request(
			"POST",
			"/orders",
			json={
				"amount": amount_paise,
				"currency": currency,
				"receipt": receipt,
				"notes": notes or {},
			},
		)
		if not isinstance(body.get("id"), str):
			raise RazorpayError("Razorpay order response is missing an identifier")
		return body

	async def order_payments(self, razorpay_order_id: str) -> list[dict[str, object]]:
		body = await self._request("GET", f"/orders/{razorpay_order_id}/payments")
		items = body.get("items")
		if not isinstance(items, list):
			raise RazorpayError("Razorpay payments response is malformed")
		return [item for item in items if isinstance(item, dict)]

	async def _request(self, method: str, path: str, **kwargs: object) -> dict[str, object]:
		try:
			async with httpx.AsyncClient(
				timeout=self._timeout_seconds,
				transport=self._transport,
				auth=self._auth,
			) as client:
				response = await client.request(method, self._base_url + path, **kwargs)  # type: ignore[arg-type]
		except httpx.HTTPError as error:
			raise RazorpayUnavailableError("Razorpay request failed") from error
		try:
			body = response.json()
		except ValueError as error:
			raise RazorpayError(
				f"Razorpay returned invalid JSON ({response.status_code})"
			) from error
		if not isinstance(body, dict):
			raise RazorpayError("Razorpay returned an unexpected response shape")
		if response.status_code >= 400:
			description = ""
			error = body.get("error")
			if isinstance(error, dict):
				description = str(cast(dict[str, object], error).get("description", ""))
			raise RazorpayError(description or f"Razorpay returned HTTP {response.status_code}")
		return body


def payment_entity(payload: dict[str, object]) -> dict[str, object]:
	entity = payload.get("payload")
	if isinstance(entity, dict):
		payment = entity.get("payment")
		if isinstance(payment, dict):
			inner = cast(dict[str, object], payment).get("entity")
			if isinstance(inner, dict):
				return inner
	return {}


def refund_entities(payment: dict[str, object]) -> list[dict[str, object]]:
	refunds = payment.get("refunds")
	if not isinstance(refunds, list):
		return []
	return [refund for refund in refunds if isinstance(refund, dict)]
