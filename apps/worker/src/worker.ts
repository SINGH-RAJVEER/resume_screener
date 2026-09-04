import type { Database } from "@skillsignal/server-core/db";
import { claimJob, finishJob, updateLease, type ClaimedJob } from "@skillsignal/server-core/queue";
import { loadVocabulary } from "./domain/vocabulary.ts";
import { topLexicalMatches } from "./domain/lexical.ts";
import { textHash, topSemanticMatches } from "./domain/semantic.ts";
import { evaluate, refineAssessments, summarize } from "./domain/evaluation.ts";
import { independentReport } from "./domain/independent.ts";
import { prepareDocument } from "./documents/processing.ts";
import { renderResumeDocx } from "./documents/renderer.ts";
import { compileJobDescription } from "./job-descriptions/compiler.ts";
import { extractJobRequirements } from "./job-descriptions/extractor.ts";
import { extractResumeFacts, assessRequirements } from "./extraction/extractor.ts";
import { join, resolve } from "node:path";
import { sql } from "drizzle-orm";
import { OpenRouterClient, OpenRouterError, OpenRouterRetryableError } from "./openrouter.ts";
import { settlePoints } from "./billing/settlement.ts";
import {
	ASSESSMENT_PROMPT_VERSION,
	EXTRACTION_PROMPT_VERSION,
	JOB_REQUIREMENTS_COMPILER_VERSION,
	JOB_REQUIREMENTS_PROMPT_VERSION,
	LOCAL_PARSER_VERSION,
	PARSER_CONFIGURATION_VERSION,
	REQUIREMENT_ASSESSMENT_SCHEMA_VERSION,
	RESUME_FACTS_SCHEMA_VERSION,
	SCORING_POLICY_VERSION,
} from "@skillsignal/server-core/versions";

export class NonRetryableJobError extends Error {}
export class RetryableJobError extends Error {}

type Processor = (job: ClaimedJob) => Promise<void>;
type JsonRecord = Record<string, unknown>;

const DETERMINISTIC_EXTRACTION_WARNING = "Structured extraction was unavailable; only deterministic facts were used";
const ASSESSMENT_UNAVAILABLE_DEGRADATION = "Model assessment was unavailable; deterministic outcomes were used";
const ASSESSMENT_FAILURE_DEGRADATION = "Model assessment failed after retries; deterministic outcomes were used";

const retryDelay = (attempt: number): number => Math.min(300, 2 ** attempt) * 1000 + Math.random() * 1000;
const listEnv = (name: string, fallback: string): string[] =>
	(Bun.env[name] ?? fallback).split(",").map((item) => item.trim()).filter(Boolean);

export class Worker {
	private stopping = false;
	private readonly processors: Map<string, Processor>;
	private readonly db: Database;
	private readonly pollSeconds: number;
	private readonly leaseSeconds: number;
	private readonly storageRoot: string;
	private readonly openrouter: OpenRouterClient | null;
	private readonly extractionModels: string[];
	private readonly assessmentModels: string[];
	private readonly embeddingModel: string;
	private readonly maxOutputTokens: number;

	constructor(db: Database, pollSeconds: number, leaseSeconds: number, storageRoot: string) {
		this.db = db;
		this.pollSeconds = pollSeconds;
		this.leaseSeconds = leaseSeconds;
		this.storageRoot = storageRoot;
		const client = new OpenRouterClient();
		this.openrouter = client.enabled ? client : null;
		this.extractionModels = listEnv("OPENROUTER_EXTRACTION_MODELS", Bun.env["OPENROUTER_EXTRACTION_MODEL"] ?? "openai/gpt-5-mini");
		this.assessmentModels = listEnv("OPENROUTER_ASSESSMENT_MODELS", Bun.env["OPENROUTER_ASSESSMENT_MODEL"] ?? "openai/gpt-5-mini");
		this.embeddingModel = Bun.env["OPENROUTER_EMBEDDING_MODEL"] ?? listEnv("OPENROUTER_EMBEDDING_MODELS", "openai/text-embedding-3-small")[0] ?? "openai/text-embedding-3-small";
		this.maxOutputTokens = Number(Bun.env["OPENROUTER_MAX_OUTPUT_TOKENS"] ?? 4096);
		this.processors = new Map([
			["resume_processing", (job) => this.processResume(job)],
			["job_description_processing", (job) => this.processJobDescription(job)],
			["independent_evaluation_processing", (job) => this.processIndependentEvaluation(job)],
			["evaluation_processing", (job) => this.processEvaluation(job)],
		]);
	}

	stop(): void { this.stopping = true; }

	async run(): Promise<void> {
		while (!this.stopping) {
			const worked = await this.runOnce();
			if (!worked) await Bun.sleep(this.pollSeconds * 1000);
		}
	}

	async runOnce(): Promise<boolean> {
		const job = await claimJob(this.db, this.leaseSeconds);
		if (!job) return false;
		const heartbeat = this.heartbeat(job);
		try {
			const processor = this.processors.get(job.type);
			if (!processor) throw new NonRetryableJobError("Unsupported processing job type");
			this.openrouter?.resetUsage();
			await processor(job);
			await finishJob(this.db, job, "completed", null);
		} catch (cause) {
			const message = cause instanceof Error ? cause.message : "Processing failed";
			const retryable = !(cause instanceof NonRetryableJobError) && job.attemptCount < job.maximumAttempts;
			await finishJob(this.db, job, retryable ? "ready" : "dead", message, retryable ? new Date(Date.now() + retryDelay(job.attemptCount)) : undefined);
		} finally {
			heartbeat.abort();
		}
		return true;
	}

	private heartbeat(job: ClaimedJob): AbortController {
		const controller = new AbortController();
		const timer = setInterval(() => { void updateLease(this.db, job, this.leaseSeconds); }, Math.max(1000, this.leaseSeconds * 333));
		controller.signal.addEventListener("abort", () => clearInterval(timer), { once: true });
		return controller;
	}

	private async processResume(job: ClaimedJob): Promise<void> {
		const rows = await this.db.execute(sql`
			SELECT d.storage_key, d.media_type
			FROM resume_version v
			JOIN resume_document d ON d.id = v.resume_document_id
			WHERE v.id = ${job.payloadReference}
		`);
		const document = rows[0] as { storage_key: string; media_type: string } | undefined;
		if (!document) throw new NonRetryableJobError("Resume version not found");
		const prepared = await prepareDocument(await this.readStorage(document.storage_key), document.media_type);
		const blockList = prepared.artifact.blocks as unknown as Array<Record<string, unknown>>;
		const blockTexts: Record<string, string> = {};
		for (const block of blockList) blockTexts[String(block["id"])] = String(block["text"] ?? "");

		let structuredFacts: JsonRecord | null = null;
		let normalizedFacts: JsonRecord = prepared.normalizedFacts as JsonRecord;
		let extractionUsed = false;
		if (this.openrouter) {
			try {
				const extracted = await this.withExtractionFallback(blockList);
				structuredFacts = extracted;
				normalizedFacts = mergeFacts(normalizedFacts, extracted, blockList);
				extractionUsed = true;
			} catch (cause) {
				if (cause instanceof OpenRouterRetryableError) throw new RetryableJobError("Resume extraction provider failed");
				normalizedFacts = { ...normalizedFacts, warnings: [...((normalizedFacts["warnings"] as string[] | undefined) ?? []), DETERMINISTIC_EXTRACTION_WARNING] };
			}
		} else {
			normalizedFacts = { ...normalizedFacts, warnings: [...((normalizedFacts["warnings"] as string[] | undefined) ?? []), DETERMINISTIC_EXTRACTION_WARNING] };
		}

		const qualityState = prepared.artifact.quality.state;
		await this.db.execute(sql`
			UPDATE resume_version
			SET extraction_blocks = ${JSON.stringify({ blocks: blockList, metadata: prepared.artifact.metadata, quality: prepared.artifact.quality })}::jsonb,
				structured_facts = ${JSON.stringify(structuredFacts ?? {})}::jsonb,
				normalized_facts = ${JSON.stringify(normalizedFacts)}::jsonb,
				quality_state = ${qualityState}, parser_version = ${LOCAL_PARSER_VERSION},
				parser_configuration_version = ${PARSER_CONFIGURATION_VERSION}, schema_version = ${RESUME_FACTS_SCHEMA_VERSION},
				extraction_prompt_version = ${extractionUsed ? EXTRACTION_PROMPT_VERSION : null}
			WHERE id = ${job.payloadReference}
			AND EXISTS (SELECT 1 FROM processing_job WHERE id = ${job.id} AND lease_token = ${job.leaseToken} AND lease_expires_at > now())
		`);

		if (qualityState !== "ready") {
			await this.db.execute(sql`UPDATE evaluation SET status = 'complete', score = NULL, evidence_coverage = NULL, eligibility = 'needs_review', quality_state = ${qualityState}, completed_at = now() WHERE resume_version_id = ${job.payloadReference}`);
			await this.settleEmployerHolds(job.payloadReference, Number(Bun.env["MIN_POINTS_EMPLOYER_RESUME"] ?? 5), "Employer resume charge (review required)");
			return;
		}

		const contact = (normalizedFacts["contact"] ?? {}) as JsonRecord;
		await this.db.execute(sql`
			UPDATE candidate_record AS candidate
			SET full_name = COALESCE(candidate.full_name, ${stringOrNull(contact["name"])}),
				email = COALESCE(candidate.email, ${stringOrNull(contact["email"])}),
				location = COALESCE(candidate.location, ${stringOrNull(contact["location"])}), updated_at = now()
			FROM resume_submission AS submission
			WHERE submission.candidate_record_id = candidate.id
				AND submission.resume_version_id = ${job.payloadReference}
		`);

		await this.storeBlockEmbeddings(job.payloadReference, blockList);
		await this.queueEvaluations(job);
	}

	private async processJobDescription(job: ClaimedJob): Promise<void> {
		const rows = await this.db.execute(sql`SELECT source_text, source_storage_key, source_media_type FROM job_version WHERE id = ${job.payloadReference}`);
		const version = rows[0] as { source_text: string | null; source_storage_key: string | null; source_media_type: string } | undefined;
		if (!version) throw new NonRetryableJobError("Job version not found");
		let source: string;
		if (version.source_storage_key) {
			const content = await this.readStorage(version.source_storage_key);
			const prepared = await prepareDocument(content, version.source_media_type);
			source = (prepared.artifact.blocks as unknown as Array<{ text: string }>).map((block) => block.text).join("\n");
		} else if (version.source_text) {
			source = version.source_text;
		} else {
			throw new NonRetryableJobError("Job description is unavailable");
		}
		source = source.trim();
		if (!source) throw new NonRetryableJobError("Job description is empty");

		let artifact: JsonRecord;
		if (!this.openrouter) {
			artifact = compileJobDescription(source, null, { degraded: true, degradedReason: "Model extraction was unavailable; deterministic drafts require careful review" }) as JsonRecord;
		} else {
			try {
				const modelOutput = await this.withJobFallback(source);
				artifact = compileJobDescription(source, modelOutput) as JsonRecord;
			} catch (cause) {
				if (cause instanceof OpenRouterRetryableError) throw new RetryableJobError("Requirement extraction provider failed");
				artifact = compileJobDescription(source, null, { degraded: true, degradedReason: "Model extraction failed; deterministic drafts require careful review" }) as JsonRecord;
			}
		}
		await this.db.execute(sql`UPDATE job_version SET draft_requirements = ${JSON.stringify(artifact)}::jsonb, source_text = ${source}, normalized_text = ${source}, schema_version = ${String(artifact["schemaVersion"] ?? "2")}, prompt_version = ${JOB_REQUIREMENTS_PROMPT_VERSION}, compiler_version = ${JOB_REQUIREMENTS_COMPILER_VERSION} WHERE id = ${job.payloadReference} AND EXISTS (SELECT 1 FROM processing_job WHERE id = ${job.id} AND lease_token = ${job.leaseToken} AND lease_expires_at > now())`);
	}

	private async processIndependentEvaluation(job: ClaimedJob): Promise<void> {
		const rows = await this.db.execute(sql`SELECT storage_key, media_type, job_description, job_description_key, job_description_media_type FROM independent_evaluation WHERE id = ${job.payloadReference}`);
		const evaluation = rows[0] as { storage_key: string; media_type: string; job_description: string | null; job_description_key: string | null; job_description_media_type: string | null } | undefined;
		if (!evaluation) throw new NonRetryableJobError("Independent evaluation not found");
		await this.db.execute(sql`UPDATE independent_evaluation SET status = 'processing', safe_error = NULL WHERE id = ${job.payloadReference}`);
		const prepared = await prepareDocument(await this.readStorage(evaluation.storage_key), evaluation.media_type);
		if (prepared.artifact.quality.state !== "ready") {
			throw new NonRetryableJobError(`Resume could not be read reliably. ${prepared.artifact.quality.warnings.join("; ")}. Upload a clearer digital document`);
		}
		const blockList = prepared.artifact.blocks as unknown as Array<Record<string, unknown>>;
		let normalizedFacts = prepared.normalizedFacts as JsonRecord;
		let jobDescription = evaluation.job_description;
		if (evaluation.job_description_key) {
			const content = await this.readStorage(evaluation.job_description_key);
			const jdPrepared = await prepareDocument(content, evaluation.job_description_media_type ?? "text/plain");
			jobDescription = (jdPrepared.artifact.blocks as unknown as Array<{ text: string }>).map((block) => block.text).join("\n").trim() || null;
		}

		let extractionUsed = false;
		let modelSuggestions: Array<Record<string, unknown>> = [];
		if (this.openrouter) {
			try {
				const extracted = await this.withExtractionFallback(blockList);
				normalizedFacts = mergeFacts(normalizedFacts, extracted, blockList);
				modelSuggestions = Array.isArray(extracted["suggestions"]) ? extracted["suggestions"] as Array<Record<string, unknown>> : [];
				extractionUsed = true;
			} catch (cause) {
				if (cause instanceof OpenRouterRetryableError) throw new RetryableJobError("Resume extraction provider failed");
				normalizedFacts = { ...normalizedFacts, warnings: [...((normalizedFacts["warnings"] as string[] | undefined) ?? []), DETERMINISTIC_EXTRACTION_WARNING] };
			}
		} else {
			normalizedFacts = { ...normalizedFacts, warnings: [...((normalizedFacts["warnings"] as string[] | undefined) ?? []), DETERMINISTIC_EXTRACTION_WARNING] };
		}

		const report = independentReport(normalizedFacts as unknown as Parameters<typeof independentReport>[0], jobDescription);
		const suggestions = mergeSuggestions(
			report.suggestions.map((item) => ({ title: item.title, detail: item.detail })),
			modelSuggestions.map((item) => ({ title: String(item["title"] ?? ""), detail: String(item["detail"] ?? "") })),
		);
		const improvedKey = `independent-resumes/improved/${job.payloadReference}.docx`;
		try {
			await this.writeStorage(improvedKey, await renderResumeDocx(normalizedFacts, suggestions));
		} catch {
			await this.db.execute(sql`UPDATE independent_evaluation SET status = 'complete', score = ${report.score}, suggestions = ${JSON.stringify(suggestions)}::jsonb, normalized_facts = ${JSON.stringify(normalizedFacts)}::jsonb, job_description = COALESCE(job_description, ${jobDescription}), improved_resume_key = NULL, improved_resume_unlocked_at = NULL, parser_version = ${LOCAL_PARSER_VERSION}, parser_configuration_version = ${PARSER_CONFIGURATION_VERSION}, schema_version = ${RESUME_FACTS_SCHEMA_VERSION}, extraction_prompt_version = ${extractionUsed ? EXTRACTION_PROMPT_VERSION : null}, scoring_policy_version = ${SCORING_POLICY_VERSION}, safe_error = NULL, completed_at = now() WHERE id = ${job.payloadReference}`);
			await this.settleIndependentHold(job.payloadReference);
			return;
		}
		await this.db.execute(sql`UPDATE independent_evaluation SET status = 'complete', score = ${report.score}, suggestions = ${JSON.stringify(suggestions)}::jsonb, normalized_facts = ${JSON.stringify(normalizedFacts)}::jsonb, job_description = COALESCE(job_description, ${jobDescription}), improved_resume_key = ${improvedKey}, improved_resume_unlocked_at = now(), parser_version = ${LOCAL_PARSER_VERSION}, parser_configuration_version = ${PARSER_CONFIGURATION_VERSION}, schema_version = ${RESUME_FACTS_SCHEMA_VERSION}, extraction_prompt_version = ${extractionUsed ? EXTRACTION_PROMPT_VERSION : null}, scoring_policy_version = ${SCORING_POLICY_VERSION}, safe_error = NULL, completed_at = now() WHERE id = ${job.payloadReference}`);
		await this.settleIndependentHold(job.payloadReference);
	}

	private async processEvaluation(job: ClaimedJob): Promise<void> {
		await this.db.execute(sql`UPDATE batch_evaluation AS batch SET model_configuration = ${JSON.stringify({ extractionModel: this.extractionModels[0], assessmentModel: this.assessmentModels[0], embeddingModel: this.embeddingModel, llmEnabled: Boolean(this.openrouter) })}::jsonb FROM evaluation WHERE evaluation.id = ${job.payloadReference} AND batch.id = evaluation.batch_evaluation_id AND batch.model_configuration = '{}'::jsonb`);
		const rows = await this.db.execute(sql`SELECT evaluation.resume_version_id, version.normalized_facts, version.extraction_blocks FROM evaluation JOIN resume_version AS version ON version.id = evaluation.resume_version_id WHERE evaluation.id = ${job.payloadReference}`);
		const evaluation = rows[0] as { resume_version_id: string; normalized_facts: JsonRecord | null; extraction_blocks: JsonRecord | null } | undefined;
		if (!evaluation) throw new NonRetryableJobError("Evaluation not found");
		const requirements = await this.db.execute(sql`SELECT id, kind, weight, normalized_text, category, assessability, predicate FROM evaluation JOIN job_requirement AS requirement ON requirement.job_version_id = evaluation.job_version_id WHERE evaluation.id = ${job.payloadReference}`);
		const requirementList = requirements as unknown as Array<Record<string, unknown>>;
		const normalizedFacts = evaluation.normalized_facts ?? {};
		const deterministic = evaluate(normalizedFacts as unknown as Parameters<typeof evaluate>[0], requirementList as unknown as Parameters<typeof evaluate>[1]);
		let assessments = [...deterministic.assessments];
		let modelUsed = false;
		let degradation: string | null = ASSESSMENT_UNAVAILABLE_DEGRADATION;
		const assessable = requirementList.filter((item) => item["assessability"] === "resume_evidence" && item["kind"] !== "ignored");
		const blocks = ((evaluation.extraction_blocks as JsonRecord | null)?.["blocks"] as Array<Record<string, unknown>> | undefined) ?? [];
		const blockTexts: Record<string, string> = {};
		for (const block of blocks) blockTexts[String(block["id"])] = String(block["text"] ?? "");
		if (!this.openrouter) {
			degradation = assessable.length ? ASSESSMENT_UNAVAILABLE_DEGRADATION : null;
		} else if (assessable.length) {
			try {
				const modelAssessments = await this.withAssessmentFallback(assessable, blocks);
				assessments = refineAssessments(deterministic.assessments, modelAssessments as unknown as Parameters<typeof refineAssessments>[1], requirementList as unknown as Parameters<typeof refineAssessments>[2]);
				modelUsed = true;
				degradation = null;
			} catch (cause) {
				if (cause instanceof OpenRouterRetryableError) throw new RetryableJobError("Requirement assessment provider failed");
				degradation = ASSESSMENT_FAILURE_DEGRADATION;
			}
		} else {
			degradation = null;
		}
		const outcome = summarize(assessments, requirementList as unknown as Parameters<typeof summarize>[1]);
		const semanticEvidence = await this.retrieveSemanticEvidence(evaluation.resume_version_id, requirementList);
		const lexicalEvidence: Record<string, JsonRecord> = {};
		for (const requirement of requirementList) {
			const matches = topLexicalMatches(String(requirement["normalized_text"] ?? ""), blockTexts);
			if (matches.length) lexicalEvidence[String(requirement["id"])] = { matches };
		}
		await this.db.transaction(async (tx) => {
			for (const assessment of outcome.assessments) {
				await tx.execute(sql`INSERT INTO requirement_assessment (id, evaluation_id, job_requirement_id, outcome, confidence, reasoning, evidence, semantic_evidence, lexical_evidence, created_at) VALUES (${crypto.randomUUID()}, ${job.payloadReference}, ${assessment.requirementId}, ${assessment.outcome}, ${assessment.confidence}, ${assessment.reasoning}, ${JSON.stringify(assessment.evidence)}::jsonb, ${JSON.stringify(semanticEvidence[assessment.requirementId] ?? null)}::jsonb, ${JSON.stringify(lexicalEvidence[assessment.requirementId] ?? null)}::jsonb, now()) ON CONFLICT (evaluation_id, job_requirement_id) DO NOTHING`);
			}
			await tx.execute(sql`UPDATE evaluation SET status = 'complete', score = ${outcome.score}, evidence_coverage = ${outcome.evidenceCoverage}, eligibility = ${outcome.eligibility}, quality_state = 'ready', scoring_policy_version = ${SCORING_POLICY_VERSION}, assessment_schema_version = ${modelUsed ? REQUIREMENT_ASSESSMENT_SCHEMA_VERSION : null}, assessment_prompt_version = ${modelUsed ? ASSESSMENT_PROMPT_VERSION : null}, assessment_degradation = ${degradation}, completed_at = now() WHERE id = ${job.payloadReference} AND EXISTS (SELECT 1 FROM processing_job WHERE id = ${job.id} AND lease_token = ${job.leaseToken} AND lease_expires_at > now())`);
		});
		await this.settleEmployerEvaluationHold(job.payloadReference);
	}

	private async withExtractionFallback(blocks: Array<Record<string, unknown>>): Promise<JsonRecord> {
		if (!this.openrouter) throw new OpenRouterError("OpenRouter is not configured");
		let lastError: unknown = null;
		for (const model of this.extractionModels) {
			try {
				return await extractResumeFacts(this.openrouter, { model, blocks, maxOutputTokens: this.maxOutputTokens });
			} catch (cause) {
				lastError = cause;
				if (cause instanceof OpenRouterError && !(cause instanceof OpenRouterRetryableError)) break;
			}
		}
		throw lastError instanceof Error ? lastError : new Error("Extraction failed");
	}

	private async withJobFallback(sourceText: string): Promise<JsonRecord> {
		if (!this.openrouter) throw new OpenRouterError("OpenRouter is not configured");
		let lastError: unknown = null;
		for (const model of this.extractionModels) {
			try {
				return await extractJobRequirements(this.openrouter, { model, sourceText, maxOutputTokens: this.maxOutputTokens });
			} catch (cause) {
				lastError = cause;
				if (cause instanceof OpenRouterError && !(cause instanceof OpenRouterRetryableError)) break;
			}
		}
		throw lastError instanceof Error ? lastError : new Error("Job extraction failed");
	}

	private async withAssessmentFallback(requirements: Array<Record<string, unknown>>, blocks: Array<Record<string, unknown>>): Promise<Array<Record<string, unknown>>> {
		if (!this.openrouter) throw new OpenRouterError("OpenRouter is not configured");
		let lastError: unknown = null;
		for (const model of this.assessmentModels) {
			try {
				return await assessRequirements(this.openrouter, { model, requirement: requirements, blocks, maxOutputTokens: this.maxOutputTokens });
			} catch (cause) {
				lastError = cause;
				if (cause instanceof OpenRouterError && !(cause instanceof OpenRouterRetryableError)) break;
			}
		}
		throw lastError instanceof Error ? lastError : new Error("Assessment failed");
	}

	private async retrieveSemanticEvidence(versionId: string, requirements: Array<Record<string, unknown>>): Promise<Record<string, JsonRecord>> {
		if (!this.openrouter || !requirements.length) return {};
		const rows = await this.db.execute(sql`SELECT block_id, vector FROM resume_block_embedding WHERE resume_version_id = ${versionId} AND model = ${this.embeddingModel}`);
		const blockVectors: Record<string, number[]> = {};
		for (const row of rows as unknown as Array<{ block_id: string; vector: number[] }>) blockVectors[row.block_id] = row.vector;
		if (!Object.keys(blockVectors).length) return {};
		try {
			const vectors = await this.openrouter.embedTexts(this.embeddingModel, requirements.map((item) => String(item["normalized_text"] ?? "")));
			const retrieved: Record<string, JsonRecord> = {};
			requirements.forEach((requirement, index) => {
				const matches = topSemanticMatches(vectors[index] as number[], blockVectors);
				if (matches.length) retrieved[String(requirement["id"])] = { model: this.embeddingModel, matches };
			});
			return retrieved;
		} catch {
			return {};
		}
	}

	private async storeBlockEmbeddings(versionId: string, blocks: Array<Record<string, unknown>>): Promise<void> {
		if (!this.openrouter) return;
		const texts = blocks.map((block) => String(block["text"] ?? ""));
		if (!texts.length) return;
		try {
			const vectors = await this.openrouter.embedTexts(this.embeddingModel, texts);
			for (let index = 0; index < blocks.length; index++) {
				const blockId = String(blocks[index]?.["id"] ?? "");
				const vector = vectors[index] as number[];
				if (!blockId || !vector) continue;
				const hash = textHash(texts[index] as string);
				await this.db.execute(sql`INSERT INTO embedding_cache (text_hash, model, vector, created_at) VALUES (${hash}, ${this.embeddingModel}, ${JSON.stringify(vector)}::jsonb, now()) ON CONFLICT (text_hash) DO NOTHING`);
				await this.db.execute(sql`INSERT INTO resume_block_embedding (resume_version_id, block_id, model, text_hash, vector, created_at) VALUES (${versionId}, ${blockId}, ${this.embeddingModel}, ${hash}, ${JSON.stringify(vector)}::jsonb, now()) ON CONFLICT (resume_version_id, block_id, model) DO UPDATE SET vector = EXCLUDED.vector, text_hash = EXCLUDED.text_hash`);
			}
		} catch {
			return;
		}
	}

	private async queueEvaluations(job: ClaimedJob): Promise<void> {
		const evaluations = await this.db.execute(sql`SELECT id FROM evaluation WHERE resume_version_id = ${job.payloadReference} AND status = 'pending'`);
		for (const row of evaluations as unknown as Array<{ id: string }>) {
			await this.db.execute(sql`INSERT INTO processing_job (id, type, status, payload_reference, idempotency_key, attempt_count, maximum_attempts, available_at, created_at, updated_at) VALUES (${crypto.randomUUID()}, 'evaluation_processing', 'ready', ${row.id}, ${row.id}, 0, 3, now(), now(), now()) ON CONFLICT (type, idempotency_key) DO NOTHING`);
		}
	}

	private async settleIndependentHold(evaluationId: string): Promise<void> {
		const rows = await this.db.execute(sql`SELECT point_reservation_id FROM independent_evaluation WHERE id = ${evaluationId}`);
		const reservationId = (rows[0] as { point_reservation_id: string | null } | undefined)?.point_reservation_id;
		if (!reservationId) return;
		const usage = this.openrouter?.usage() ?? { promptTokens: 0, completionTokens: 0, costUsd: 0 };
		const charge = settlePoints(usage.promptTokens, usage.completionTokens, usage.costUsd, "independent_evaluation", {
			pointsPerUsd: Number(Bun.env["POINTS_PER_USD"] ?? 1000),
			minimumIndependentEvaluationPoints: Number(Bun.env["MIN_POINTS_INDEPENDENT_EVALUATION"] ?? 10),
			minimumEmployerResumePoints: Number(Bun.env["MIN_POINTS_EMPLOYER_RESUME"] ?? 5),
			priceCeilingUsdPerMillionInput: Number(Bun.env["PRICE_CEILING_INPUT_USD_PER_MILLION"] ?? 3),
			priceCeilingUsdPerMillionOutput: Number(Bun.env["PRICE_CEILING_OUTPUT_USD_PER_MILLION"] ?? 15),
		});
		await this.db.execute(sql`INSERT INTO point_ledger_entry (id, account_id, amount, reason, idempotency_key) SELECT ${crypto.randomUUID()}, account_id, ${-Math.min(charge, 1000000)}, 'Independent evaluation charge', ${`settle:${reservationId}`} FROM point_reservation WHERE id = ${reservationId} AND state = 'reserved' ON CONFLICT (account_id, idempotency_key) DO NOTHING`);
		await this.db.execute(sql`UPDATE point_reservation SET state = 'settled', updated_at = now() WHERE id = ${reservationId} AND state = 'reserved'`);
	}

	private async settleEmployerEvaluationHold(evaluationId: string): Promise<void> {
		const rows = await this.db.execute(sql`SELECT point_reservation_id FROM evaluation WHERE id = ${evaluationId}`);
		const reservationId = (rows[0] as { point_reservation_id: string | null } | undefined)?.point_reservation_id;
		if (!reservationId) return;
		const usage = this.openrouter?.usage() ?? { promptTokens: 0, completionTokens: 0, costUsd: 0 };
		const charge = settlePoints(usage.promptTokens, usage.completionTokens, usage.costUsd, "employer_resume", {
			pointsPerUsd: Number(Bun.env["POINTS_PER_USD"] ?? 1000),
			minimumIndependentEvaluationPoints: Number(Bun.env["MIN_POINTS_INDEPENDENT_EVALUATION"] ?? 10),
			minimumEmployerResumePoints: Number(Bun.env["MIN_POINTS_EMPLOYER_RESUME"] ?? 5),
			priceCeilingUsdPerMillionInput: Number(Bun.env["PRICE_CEILING_INPUT_USD_PER_MILLION"] ?? 3),
			priceCeilingUsdPerMillionOutput: Number(Bun.env["PRICE_CEILING_OUTPUT_USD_PER_MILLION"] ?? 15),
		});
		await this.db.execute(sql`INSERT INTO point_ledger_entry (id, account_id, amount, reason, idempotency_key) SELECT ${crypto.randomUUID()}, account_id, ${-Math.min(charge, 1000000)}, 'Employer resume charge', ${`settle:${reservationId}`} FROM point_reservation WHERE id = ${reservationId} AND state = 'reserved' ON CONFLICT (account_id, idempotency_key) DO NOTHING`);
		await this.db.execute(sql`UPDATE point_reservation SET state = 'settled', updated_at = now() WHERE id = ${reservationId} AND state = 'reserved'`);
	}

	private async settleEmployerHolds(versionId: string, minimum: number, reason: string): Promise<void> {
		const rows = await this.db.execute(sql`SELECT point_reservation_id FROM evaluation WHERE resume_version_id = ${versionId} AND point_reservation_id IS NOT NULL`);
		for (const row of rows as unknown as Array<{ point_reservation_id: string }>) {
			await this.db.execute(sql`INSERT INTO point_ledger_entry (id, account_id, amount, reason, idempotency_key) SELECT ${crypto.randomUUID()}, account_id, ${-minimum}, ${reason}, ${`settle:${row.point_reservation_id}`} FROM point_reservation WHERE id = ${row.point_reservation_id} AND state = 'reserved' ON CONFLICT (account_id, idempotency_key) DO NOTHING`);
			await this.db.execute(sql`UPDATE point_reservation SET state = 'settled', updated_at = now() WHERE id = ${row.point_reservation_id} AND state = 'reserved'`);
		}
	}

	private async readStorage(key: string): Promise<Uint8Array> {
		const root = resolve(this.storageRoot);
		const path = resolve(join(root, key));
		if (!path.startsWith(`${root}/`)) throw new NonRetryableJobError("Storage key escapes the configured root");
		const file = Bun.file(path); if (!(await file.exists())) throw new NonRetryableJobError("Source document is unavailable");
		return new Uint8Array(await file.arrayBuffer());
	}

	private async writeStorage(key: string, content: Uint8Array): Promise<void> {
		const root = resolve(this.storageRoot);
		const path = resolve(join(root, key));
		if (!path.startsWith(`${root}/`)) throw new NonRetryableJobError("Storage key escapes the configured root");
		await Bun.write(path, content);
	}
}

const stringOrNull = (value: unknown): string | null =>
	typeof value === "string" && value.trim() ? value : null;

type FactEntry = Record<string, unknown>;

const factEntries = (value: unknown): FactEntry[] =>
	Array.isArray(value) ? value.filter((item): item is FactEntry => typeof item === "object" && item !== null && !Array.isArray(item)) : [];

export const mergeFacts = (deterministic: JsonRecord, extracted: JsonRecord, blocks: readonly FactEntry[]): JsonRecord => {
	const vocabulary = loadVocabulary();
	const merged = new Map<string, FactEntry>();
	for (const skill of factEntries((deterministic["skills"] as FactEntry[] | undefined) ?? (deterministic as unknown as { skills?: unknown })["skills"])) {
		const name = String((skill["canonicalName"] as string | undefined) ?? "");
		if (!name) continue;
		merged.set(name.toLowerCase(), { canonicalName: name, category: skill["category"], evidenceBlockIds: skill["evidenceBlockIds"] ?? [] });
	}
	const order = new Map(blocks.map((block, index) => [String(block["id"]), index]));
	for (const skill of factEntries(extracted["skills"])) {
		const source = String(skill["canonicalName"] ?? "").trim();
		if (!source || merged.has(source.toLowerCase())) continue;
		const canonical = vocabulary.phraseToCanonical.get(source.toLowerCase()) ?? source;
		if (merged.has(canonical.toLowerCase())) continue;
		const references = [...new Set(factEntries(skill["evidence"]).map((entry) => String(entry["blockId"] ?? "")).filter(Boolean))].sort((a, b) => (order.get(a) ?? blocks.length) - (order.get(b) ?? blocks.length));
		merged.set(canonical.toLowerCase(), { canonicalName: canonical, category: vocabulary.categories.get(canonical.toLowerCase()) ?? null, evidenceBlockIds: references });
	}
	const contact = ((deterministic["contact"] ?? {}) as FactEntry);
	const extractedContact = ((extracted["contact"] ?? {}) as FactEntry);
	return {
		contact: {
			name: contact["name"] ?? extractedContact["name"] ?? null,
			email: contact["email"] ?? extractedContact["email"] ?? null,
			phone: contact["phone"] ?? extractedContact["phone"] ?? null,
			location: contact["location"] ?? extractedContact["location"] ?? null,
		},
		skills: [...merged.values()].sort((a, b) => String(a["canonicalName"]).toLowerCase().localeCompare(String(b["canonicalName"]).toLowerCase())),
		employment: factEntries(extracted["employment"]),
		education: factEntries(extracted["education"]),
		certifications: factEntries(extracted["certifications"]),
		warnings: [...new Set([...factEntries(extracted["warnings"]).map(String), ...((deterministic["warnings"] as string[] | undefined) ?? [])])].filter((item): item is string => typeof item === "string"),
	};
};

export const mergeSuggestions = (deterministic: readonly { title: string; detail?: unknown }[], extracted: readonly { title: unknown; detail?: unknown }[], limit = 10): Array<{ title: string; detail: string }> => {
	const merged = new Map<string, { title: string; detail: string }>();
	for (const suggestion of [...deterministic, ...extracted]) {
		const title = String(suggestion.title ?? "").trim();
		if (!title || merged.has(title.toLowerCase())) continue;
		merged.set(title.toLowerCase(), { title, detail: String(suggestion.detail ?? "") });
	}
	return [...merged.values()].slice(0, limit);
};
