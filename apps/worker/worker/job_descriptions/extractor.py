import json
from collections.abc import Mapping

from pydantic import ValidationError

from ..extraction.schemas import strict_schema
from ..providers.openrouter import OpenRouterClient, OpenRouterError
from .compiler import blocks_for_model, source_blocks
from .prompt import JOB_REQUIREMENTS_SYSTEM_PROMPT
from .schemas import ModelRequirementExtraction


async def extract_job_requirements(
	client: OpenRouterClient,
	*,
	model: str,
	source_text: str,
	max_output_tokens: int = 4096,
) -> dict[str, object]:
	blocks = blocks_for_model(source_blocks(source_text))
	user_content = {
		"documentType": "job_description",
		"blocks": blocks,
	}
	raw = await client.complete_json(
		model=model,
		system_prompt=JOB_REQUIREMENTS_SYSTEM_PROMPT,
		user_parts=(
			"<job_description_data>\n"
			+ json.dumps(user_content, ensure_ascii=False)
			+ "\n</job_description_data>"
		),
		schema_name="job_requirement_drafts",
		schema=strict_schema(ModelRequirementExtraction),
		max_output_tokens=max_output_tokens,
	)
	return validate_model_extraction(raw)


def validate_model_extraction(raw: Mapping[str, object]) -> dict[str, object]:
	try:
		extraction = ModelRequirementExtraction.model_validate(raw)
	except ValidationError as error:
		raise OpenRouterError("Model job requirements do not match the schema") from error
	return extraction.model_dump(by_alias=True)
