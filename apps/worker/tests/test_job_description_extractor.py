import json
from typing import cast

import httpx
import pytest

from worker.job_descriptions.extractor import extract_job_requirements
from worker.providers.openrouter import OpenRouterClient, OpenRouterError


def model_output() -> dict[str, object]:
	return {
		"requirements": [
			{
				"normalizedText": "Python experience",
				"category": "skill",
				"suggestedKind": "required",
				"sourceModality": "section_required",
				"assessability": "resume_evidence",
				"predicate": {
					"operator": "all_of",
					"criteria": [
						{
							"type": "skill",
							"canonicalName": "Python",
							"minimumMonths": None,
							"minimumLevel": None,
							"subjects": [],
						}
					],
				},
				"evidence": [{"blockId": "jd-b1", "quote": "Python experience"}],
				"confidence": 0.9,
			}
		],
		"warnings": [],
	}


@pytest.mark.asyncio
async def test_extractor_requests_strict_grounded_output() -> None:
	requests: list[dict[str, object]] = []

	def handler(request: httpx.Request) -> httpx.Response:
		requests.append(cast(dict[str, object], json.loads(request.content)))
		return httpx.Response(
			200,
			json={
				"choices": [
					{
						"finish_reason": "stop",
						"message": {"content": json.dumps(model_output())},
					}
				]
			},
		)

	client = OpenRouterClient(
		api_key="key",
		transport=httpx.MockTransport(handler),
	)
	result = await extract_job_requirements(
		client,
		model="openai/gpt-5-mini",
		source_text="Requirements\n- Python experience",
	)

	assert result == model_output()
	payload = requests[0]
	response_format = cast(dict[str, object], payload["response_format"])
	json_schema = cast(dict[str, object], response_format["json_schema"])
	assert json_schema["strict"] is True
	messages = cast(list[dict[str, object]], payload["messages"])
	assert "jd-b1" in str(messages[1]["content"])
	assert "Never create a hard gate" in str(messages[0]["content"])


@pytest.mark.asyncio
async def test_extractor_rejects_invalid_local_schema() -> None:
	def handler(request: httpx.Request) -> httpx.Response:
		return httpx.Response(
			200,
			json={
				"choices": [
					{
						"finish_reason": "stop",
						"message": {"content": '{"requirements": [], "warnings": [1]}'},
					}
				]
			},
		)

	client = OpenRouterClient(api_key="key", transport=httpx.MockTransport(handler))
	with pytest.raises(OpenRouterError, match="do not match the schema"):
		await extract_job_requirements(
			client,
			model="openai/gpt-5-mini",
			source_text="Requirements\n- Python experience",
		)
