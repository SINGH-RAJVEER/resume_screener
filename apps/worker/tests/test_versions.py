from worker.job_descriptions.compiler import compile_job_description
from worker.versions import (
	ASSESSMENT_PROMPT_VERSION,
	EXTRACTION_PROMPT_VERSION,
	JOB_REQUIREMENTS_COMPILER_VERSION,
	JOB_REQUIREMENTS_PROMPT_VERSION,
	JOB_REQUIREMENTS_SCHEMA_VERSION,
	LOCAL_PARSER_VERSION,
	PARSER_CONFIGURATION_VERSION,
	REQUIREMENT_ASSESSMENT_SCHEMA_VERSION,
	RESUME_FACTS_SCHEMA_VERSION,
	SCORING_POLICY_VERSION,
)


def test_all_persisted_artifact_versions_are_explicit() -> None:
	assert {
		ASSESSMENT_PROMPT_VERSION,
		EXTRACTION_PROMPT_VERSION,
		JOB_REQUIREMENTS_COMPILER_VERSION,
		JOB_REQUIREMENTS_PROMPT_VERSION,
		JOB_REQUIREMENTS_SCHEMA_VERSION,
		LOCAL_PARSER_VERSION,
		PARSER_CONFIGURATION_VERSION,
		REQUIREMENT_ASSESSMENT_SCHEMA_VERSION,
		RESUME_FACTS_SCHEMA_VERSION,
		SCORING_POLICY_VERSION,
	} == {
		"1",
		"2",
		"compiler-2",
		"local-2",
		"resume-parser-2",
		"criterion-weighted-1",
	}


def test_job_compiler_artifact_records_its_versions() -> None:
	artifact = compile_job_description("Requirements\n- Python is required")

	assert artifact["schemaVersion"] == JOB_REQUIREMENTS_SCHEMA_VERSION
	assert artifact["promptVersion"] == JOB_REQUIREMENTS_PROMPT_VERSION
	assert artifact["compilerVersion"] == JOB_REQUIREMENTS_COMPILER_VERSION
