import base64
import json
from collections.abc import Sequence
from typing import cast

import httpx

RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504, 529}
RETRYABLE_ERROR_CODES = {
	"rate_limit_exceeded",
	"provider_overloaded",
	"provider_unavailable",
	"timeout",
}


class OpenRouterError(Exception):
	"""Non-retryable provider failure: request, schema, or refusal problem."""


class OpenRouterRetryableError(OpenRouterError):
	"""Transient provider failure that a bounded job retry may resolve."""


def document_file_part(
	filename: str, content: bytes, media_type: str
) -> dict[str, object] | None:
	# OpenRouter forwards PDFs natively to file-capable models; DOCX and TXT
	# are not file-input formats, so callers send their extracted text only.
	if media_type != "application/pdf":
		return None
	data_url = "data:application/pdf;base64," + base64.b64encode(content).decode()
	return {"type": "file", "file": {"filename": filename, "file_data": data_url}}


class OpenRouterClient:
	def __init__(
		self,
		api_key: str,
		base_url: str = "https://openrouter.ai/api/v1",
		timeout_seconds: float = 90.0,
		transport: httpx.AsyncBaseTransport | None = None,
	) -> None:
		self._base_url = base_url.rstrip("/")
		self._chat_completions_url = self._base_url + "/chat/completions"
		self._timeout_seconds = timeout_seconds
		self._transport = transport
		self._headers = {
			"Authorization": f"Bearer {api_key}",
			"Content-Type": "application/json",
			"X-Title": "resume-screener",
		}

	async def complete_json(
		self,
		*,
		model: str,
		system_prompt: str,
		user_parts: Sequence[dict[str, object]] | str,
		schema_name: str,
		schema: dict[str, object],
		max_output_tokens: int,
	) -> dict[str, object]:
		payload: dict[str, object] = {
			"model": model,
			"messages": [
				{"role": "system", "content": system_prompt},
				{
					"role": "user",
					"content": user_parts if isinstance(user_parts, str) else list(user_parts),
				},
			],
			"response_format": {
				"type": "json_schema",
				"json_schema": {"name": schema_name, "strict": True, "schema": schema},
			},
			"max_tokens": max_output_tokens,
			# require_parameters keeps routing on endpoints that honor the JSON
			# schema; deny keeps resume content out of provider training.
			"provider": {"require_parameters": True, "data_collection": "deny"},
		}
		body = await self._post(payload)
		return parse_json_completion(body)

	async def embed_texts(self, *, model: str, texts: Sequence[str]) -> list[list[float]]:
		inputs: list[object] = list(texts)
		payload = cast(dict[str, object], {"model": model, "input": inputs})
		body = await self._post(payload, path="/embeddings")
		return parse_embedding_response(body)

	async def _post(
		self, payload: dict[str, object], path: str = "/chat/completions"
	) -> dict[str, object]:
		try:
			async with httpx.AsyncClient(
				timeout=self._timeout_seconds, transport=self._transport
			) as client:
				response = await client.post(
					self._base_url + path,
					json=payload,
					headers=self._headers,
				)
		except httpx.TimeoutException as error:
			raise OpenRouterRetryableError("Model request timed out") from error
		except httpx.TransportError as error:
			raise OpenRouterRetryableError("Model request transport failed") from error
		body = decode_body(response)
		if response.status_code != 200:
			error = body.get("error")
			message = error_string(error, "message")
			raise classify_status(
				response.status_code, message or f"HTTP {response.status_code}"
			)
		# OpenRouter can report upstream failures inside HTTP 200.
		if isinstance(body.get("error"), dict):
			raise classify_error(cast(dict[str, object], body["error"]))
		return body


def decode_body(response: httpx.Response) -> dict[str, object]:
	try:
		body: object = response.json()
	except ValueError as error:
		raise classify_status(response.status_code, "Model returned invalid JSON") from error
	if not isinstance(body, dict):
		raise classify_status(response.status_code, "Model response is not an object")
	return cast(dict[str, object], body)


def error_string(error: object, key: str) -> str:
	if isinstance(error, dict):
		value = cast(dict[str, object], error).get(key)
		if isinstance(value, str):
			return value
	return ""


def classify_status(status_code: int, message: str) -> OpenRouterError:
	if status_code in RETRYABLE_STATUS_CODES:
		return OpenRouterRetryableError(message)
	if status_code == 402:
		return OpenRouterError("Model credits are exhausted")
	if status_code in (401, 403):
		return OpenRouterError("Model credentials were rejected")
	return OpenRouterError(message)


def classify_error(error: dict[str, object]) -> OpenRouterError:
	code = error.get("code")
	code_text = code if isinstance(code, str) else ""
	message = error_string(error, "message") or code_text
	metadata = error.get("metadata")
	if isinstance(metadata, dict) and cast(dict[str, object], metadata).get("file_annotations"):
		# The document parsed but every provider failed; retrying would
		# re-parse and re-charge, so treat this as a plain failure.
		return OpenRouterError(message)
	if code_text in RETRYABLE_ERROR_CODES:
		return OpenRouterRetryableError(message)
	return OpenRouterError(message)


def parse_embedding_response(body: dict[str, object]) -> list[list[float]]:
	data = body.get("data")
	if not isinstance(data, list) or not data:
		raise OpenRouterError("Embedding response has no data")
	vectors: list[list[float]] = []
	for item in cast(list[object], data):
		if not isinstance(item, dict):
			raise OpenRouterError("Embedding entry is malformed")
		entry = cast(dict[str, object], item)
		index = entry.get("index")
		embedding = entry.get("embedding")
		if not isinstance(embedding, list):
			raise OpenRouterError("Embedding vector is missing")
		values: list[float] = []
		for value in cast(list[object], embedding):
			if not isinstance(value, (int, float)):
				raise OpenRouterError("Embedding vector is not numeric")
			values.append(float(value))
		if not values:
			raise OpenRouterError("Embedding vector is empty")
		position = index if isinstance(index, int) else len(vectors)
		while len(vectors) <= position:
			vectors.append([])
		vectors[position] = values
	dimensions = {len(vector) for vector in vectors}
	if len(dimensions) != 1:
		raise OpenRouterError("Embedding vectors have inconsistent dimensions")
	return vectors


def parse_json_completion(body: dict[str, object]) -> dict[str, object]:
	choices = cast(list[object], body.get("choices"))
	if not choices:
		raise OpenRouterError("Model response has no choices")
	first = choices[0]
	if not isinstance(first, dict):
		raise OpenRouterError("Model response choice is malformed")
	choice = cast(dict[str, object], first)
	finish_reason = choice.get("finish_reason")
	if finish_reason == "length":
		raise OpenRouterRetryableError("Model output was truncated")
	if finish_reason not in ("stop", None):
		raise OpenRouterError(f"Model stopped early: {finish_reason}")
	message = choice.get("message")
	content = ""
	refusal = ""
	if isinstance(message, dict):
		message_map = cast(dict[str, object], message)
		text = message_map.get("content")
		if isinstance(text, str):
			content = text
		refusal = error_string(message_map, "refusal")
	if not content.strip():
		if refusal:
			raise OpenRouterError("Model refused the extraction request")
		raise OpenRouterError("Model response is empty")
	try:
		parsed: object = json.loads(content)
	except ValueError as error:
		raise OpenRouterError("Model response is not valid JSON") from error
	if not isinstance(parsed, dict):
		raise OpenRouterError("Model response is not a JSON object")
	return cast(dict[str, object], parsed)
