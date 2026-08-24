import json

import httpx
import pytest

from worker.providers.openrouter import (
	OpenRouterClient,
	OpenRouterError,
	OpenRouterRetryableError,
	parse_json_completion,
)

SCHEMA: dict[str, object] = {
	"type": "object",
	"properties": {"answer": {"type": "string"}},
	"required": ["answer"],
	"additionalProperties": False,
}


def completion_body(content: str, finish_reason: str = "stop") -> dict[str, object]:
	return {
		"choices": [
			{
				"finish_reason": finish_reason,
				"message": {"role": "assistant", "content": content},
			}
		],
		"usage": {"prompt_tokens": 10, "completion_tokens": 5},
	}


def transport_with(
	payload: dict[str, object], status_code: int = 200
) -> tuple[httpx.MockTransport, list[dict[str, object]]]:
	requests: list[dict[str, object]] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(json.loads(request.content))
		return httpx.Response(status_code, json=payload)

	return httpx.MockTransport(handler), requests


async def test_complete_json_returns_parsed_content() -> None:
	transport, requests = transport_with(completion_body('{"answer": "yes"}'))
	client = OpenRouterClient(api_key="key", timeout_seconds=5, transport=transport)
	result = await client.complete_json(
		model="openai/gpt-5-mini",
		system_prompt="system",
		user_parts="user",
		schema_name="answer",
		schema=SCHEMA,
		max_output_tokens=256,
	)
	assert result == {"answer": "yes"}
	assert len(requests) == 1


async def test_request_carries_schema_and_privacy_preferences() -> None:
	transport, requests = transport_with(completion_body("{}"))
	client = OpenRouterClient(api_key="key", timeout_seconds=5, transport=transport)
	await client.complete_json(
		model="openai/gpt-5-mini",
		system_prompt="system",
		user_parts=[{"type": "text", "text": "user"}],
		schema_name="answer",
		schema=SCHEMA,
		max_output_tokens=256,
	)
	payload = requests[0]
	assert payload["model"] == "openai/gpt-5-mini"
	assert payload["max_tokens"] == 256
	messages = payload["messages"]
	assert isinstance(messages, list)
	assert messages[0]["role"] == "system"
	assert messages[1]["content"] == [{"type": "text", "text": "user"}]
	response_format = payload["response_format"]
	assert response_format == {
		"type": "json_schema",
		"json_schema": {"name": "answer", "strict": True, "schema": SCHEMA},
	}
	assert payload["provider"] == {"require_parameters": True, "data_collection": "deny"}


async def test_http_status_errors_are_classified() -> None:
	cases: list[tuple[int, type[Exception]]] = [
		(429, OpenRouterRetryableError),
		(503, OpenRouterRetryableError),
		(402, OpenRouterError),
		(401, OpenRouterError),
		(400, OpenRouterError),
	]
	for status_code, expected in cases:
		transport, _ = transport_with({"error": {"message": "problem"}}, status_code)
		client = OpenRouterClient(api_key="key", timeout_seconds=5, transport=transport)
		with pytest.raises(expected):
			await client.complete_json(
				model="openai/gpt-5-mini",
				system_prompt="system",
				user_parts="user",
				schema_name="answer",
				schema=SCHEMA,
				max_output_tokens=256,
			)


async def test_provider_failure_inside_success_response_is_classified() -> None:
	body: dict[str, object] = {
		"error": {"code": "provider_overloaded", "message": "overloaded"}
	}
	transport, _ = transport_with(body)
	client = OpenRouterClient(api_key="key", timeout_seconds=5, transport=transport)
	with pytest.raises(OpenRouterRetryableError):
		await client.complete_json(
			model="openai/gpt-5-mini",
			system_prompt="system",
			user_parts="user",
			schema_name="answer",
			schema=SCHEMA,
			max_output_tokens=256,
		)


async def test_transport_timeout_is_retryable() -> None:
	def handler(request: httpx.Request) -> httpx.Response:
		raise httpx.ReadTimeout("timed out")

	client = OpenRouterClient(
		api_key="key", timeout_seconds=5, transport=httpx.MockTransport(handler)
	)
	with pytest.raises(OpenRouterRetryableError):
		await client.complete_json(
			model="openai/gpt-5-mini",
			system_prompt="system",
			user_parts="user",
			schema_name="answer",
			schema=SCHEMA,
			max_output_tokens=256,
		)


def test_truncated_completion_is_retryable() -> None:
	with pytest.raises(OpenRouterRetryableError):
		parse_json_completion(completion_body("partial", "length"))


def test_refusal_is_not_retryable() -> None:
	body: dict[str, object] = {
		"choices": [
			{
				"finish_reason": "stop",
				"message": {"role": "assistant", "content": "", "refusal": "no"},
			}
		]
	}
	with pytest.raises(OpenRouterError):
		parse_json_completion(body)


async def test_embed_texts_returns_indexed_vectors() -> None:
	requests: list[dict[str, object]] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(json.loads(request.content))
		return httpx.Response(
			200,
			json={
				"data": [
					{"index": 1, "embedding": [0.2, 0.4]},
					{"index": 0, "embedding": [0.1, 0.3]},
				]
			},
		)

	client = OpenRouterClient(
		api_key="key",
		timeout_seconds=5,
		transport=httpx.MockTransport(handler),
	)
	vectors = await client.embed_texts(model="qwen/qwen3-embedding-8b", texts=["a", "b"])
	assert vectors == [[0.1, 0.3], [0.2, 0.4]]
	assert requests[0]["model"] == "qwen/qwen3-embedding-8b"


async def test_embed_texts_rejects_inconsistent_dimensions() -> None:
	def handler(request: httpx.Request) -> httpx.Response:
		return httpx.Response(
			200,
			json={
				"data": [
					{"index": 0, "embedding": [0.1]},
					{"index": 1, "embedding": [0.2, 0.3]},
				]
			},
		)

	client = OpenRouterClient(
		api_key="key",
		timeout_seconds=5,
		transport=httpx.MockTransport(handler),
	)
	with pytest.raises(OpenRouterError):
		await client.embed_texts(model="m", texts=["a", "b"])
