import { boolean, integer, jsonb, pgTable, text, timestamp, unique, primaryKey } from "drizzle-orm/pg-core";

const id = (name = "id") => text(name).primaryKey();
const createdAt = () => timestamp("created_at", { withTimezone: true }).defaultNow().notNull();

export const users = pgTable("user", {
	id: id(), name: text("name").notNull(), email: text("email").notNull(),
	accountType: text("account_type").notNull().default("candidate"),
	emailVerified: boolean("email_verified").notNull().default(false), isDemo: boolean("is_demo").notNull().default(false),
	image: text("image"), createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
}, (table) => [unique("uq_user_email").on(table.email)]);

export const accounts = pgTable("account", {
	id: id(), accountId: text("account_id").notNull(), providerId: text("provider_id").notNull(), userId: text("user_id").notNull(),
	password: text("password"), createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
}, (table) => [unique("uq_account_provider_account").on(table.providerId, table.accountId)]);

export const organizations = pgTable("organization", {
	id: id(), name: text("name").notNull(), defaultMemberRole: text("default_member_role").notNull().default("viewer"),
	retentionDays: integer("retention_days").notNull().default(90), createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const organizationMembers = pgTable("organization_member", {
	id: id(), organizationId: text("organization_id").notNull(), userId: text("user_id").notNull(), role: text("role").notNull(), createdAt: createdAt(),
}, (table) => [unique("uq_organization_member").on(table.organizationId, table.userId), unique("uq_organization_member_user").on(table.userId)]);

export const jobs = pgTable("job", {
	id: id(), organizationId: text("organization_id").notNull(), title: text("title").notNull(),
	applicationOpensAt: timestamp("application_opens_at", { withTimezone: true }), applicationClosesAt: timestamp("application_closes_at", { withTimezone: true }),
	createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const organizationEmailDomains = pgTable("organization_email_domain", {
	id: id(), organizationId: text("organization_id").notNull(), domain: text("domain").notNull(), createdAt: createdAt(),
}, (table) => [unique("uq_organization_email_domain").on(table.domain)]);

export const organizationAllowedEmails = pgTable("organization_allowed_email", {
	id: id(), organizationId: text("organization_id").notNull(), email: text("email").notNull(), createdAt: createdAt(),
}, (table) => [unique("uq_organization_allowed_email").on(table.organizationId, table.email)]);

export const jobVersions = pgTable("job_version", {
	id: id(), jobId: text("job_id").notNull(), version: integer("version").notNull(), sourceText: text("source_text"), normalizedText: text("normalized_text"),
	sourceMediaType: text("source_media_type").notNull(), sourceStorageKey: text("source_storage_key"), draftRequirements: jsonb("draft_requirements"),
	schemaVersion: text("schema_version"), promptVersion: text("prompt_version").notNull(), compilerVersion: text("compiler_version").notNull(), confirmedAt: timestamp("confirmed_at", { withTimezone: true }), createdAt: createdAt(),
}, (table) => [unique("uq_job_version").on(table.jobId, table.version)]);

export const resumeDocuments = pgTable("resume_document", {
	id: id(), ownerUserId: text("owner_user_id"), organizationId: text("organization_id"), candidateRecordId: text("candidate_record_id"), storageKey: text("storage_key").notNull(), checksum: text("checksum").notNull(), mediaType: text("media_type").notNull(), sizeBytes: integer("size_bytes").notNull(), originalName: text("original_name").notNull(), retentionDate: timestamp("retention_date", { withTimezone: true }).notNull(), createdAt: createdAt(),
});

export const jobRequirements = pgTable("job_requirement", {
	id: id(), jobVersionId: text("job_version_id").notNull(), stableId: text("stable_id").notNull(),
	kind: text("kind").notNull(), weight: integer("weight").notNull(), normalizedText: text("normalized_text").notNull(),
	category: text("category").notNull().default("other"), sourceModality: text("source_modality").notNull().default("unclear"),
	assessability: text("assessability").notNull().default("unclear"), predicate: jsonb("predicate").notNull().default({}), aliases: jsonb("aliases").notNull().default([]), sourceEvidence: jsonb("source_evidence").notNull().default([]), confirmedAt: timestamp("confirmed_at", { withTimezone: true }),
}, (table) => [unique("uq_job_requirement_stable_id").on(table.jobVersionId, table.stableId)]);

export const resumeVersions = pgTable("resume_version", {
	id: id(), organizationId: text("organization_id"), resumeDocumentId: text("resume_document_id").notNull(), version: integer("version").notNull(), extractionBlocks: jsonb("extraction_blocks"), structuredFacts: jsonb("structured_facts"), normalizedFacts: jsonb("normalized_facts"), qualityState: text("quality_state").notNull().default("pending"), parserVersion: text("parser_version"), parserConfigurationVersion: text("parser_configuration_version"), schemaVersion: text("schema_version"), extractionPromptVersion: text("extraction_prompt_version"), createdAt: createdAt(),
}, (table) => [unique("uq_resume_version").on(table.resumeDocumentId, table.version)]);

export const processingJobs = pgTable("processing_job", {
	id: id(), type: text("type").notNull(), status: text("status").notNull().default("ready"), payloadReference: text("payload_reference").notNull(), idempotencyKey: text("idempotency_key").notNull(), attemptCount: integer("attempt_count").notNull().default(0), maximumAttempts: integer("maximum_attempts").notNull().default(3), availableAt: timestamp("available_at", { withTimezone: true }).defaultNow().notNull(), leaseToken: text("lease_token"), leaseExpiresAt: timestamp("lease_expires_at", { withTimezone: true }), safeError: text("safe_error"), createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
}, (table) => [unique("uq_processing_job_idempotency").on(table.type, table.idempotencyKey)]);

export const independentEvaluations = pgTable("independent_evaluation", {
	id: id(), userId: text("user_id").notNull(), storageKey: text("storage_key").notNull(), originalName: text("original_name").notNull(), mediaType: text("media_type").notNull(), jobDescription: text("job_description"), jobDescriptionKey: text("job_description_key"), jobDescriptionMediaType: text("job_description_media_type"), status: text("status").notNull().default("queued"), score: integer("score"), suggestions: jsonb("suggestions"), improvedResumeKey: text("improved_resume_key"), normalizedFacts: jsonb("normalized_facts"), safeError: text("safe_error"), pointReservationId: text("point_reservation_id"), freeWeekStart: timestamp("free_week_start", { withTimezone: true }), retentionDate: timestamp("retention_date", { withTimezone: true }).notNull(), createdAt: createdAt(), completedAt: timestamp("completed_at", { withTimezone: true }),
});

export const candidateRecords = pgTable("candidate_record", {
	id: id(), organizationId: text("organization_id").notNull(), userId: text("user_id"), fullName: text("full_name"), email: text("email"), phone: text("phone"), location: text("location"), createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull(),
});

export const resumeSubmissions = pgTable("resume_submission", {
	id: id(), organizationId: text("organization_id").notNull(), jobId: text("job_id").notNull(), candidateRecordId: text("candidate_record_id").notNull(), resumeVersionId: text("resume_version_id").notNull(), submittingUserId: text("submitting_user_id"), createdAt: createdAt(),
});

export const batchEvaluations = pgTable("batch_evaluation", {
	id: id(), organizationId: text("organization_id").notNull(), jobId: text("job_id").notNull(), jobVersionId: text("job_version_id").notNull(), createdByUserId: text("created_by_user_id").notNull(), requirementSchemaVersion: text("requirement_schema_version").notNull(), scoringPolicyVersion: text("scoring_policy_version").notNull(), modelConfiguration: jsonb("model_configuration").notNull().default({}), createdAt: createdAt(),
});

export const evaluations = pgTable("evaluation", {
	id: id(), batchEvaluationId: text("batch_evaluation_id"), resumeSubmissionId: text("resume_submission_id").notNull(), jobVersionId: text("job_version_id").notNull(), resumeVersionId: text("resume_version_id").notNull(), status: text("status").notNull().default("pending"), score: integer("score"), evidenceCoverage: integer("evidence_coverage"), eligibility: text("eligibility").notNull().default("pending"), qualityState: text("quality_state").notNull().default("pending"), rank: integer("rank"), pointReservationId: text("point_reservation_id"), createdAt: createdAt(), completedAt: timestamp("completed_at", { withTimezone: true }),
});

export const invitations = pgTable("invitation", {
	id: id(), jobId: text("job_id").notNull(), creatorUserId: text("creator_user_id").notNull(), tokenHash: text("token_hash").notNull(), passcodeHash: text("passcode_hash"), expiresAt: timestamp("expires_at", { withTimezone: true }).notNull(), redeemingUserId: text("redeeming_user_id"), resumeSubmissionId: text("resume_submission_id"), revokedAt: timestamp("revoked_at", { withTimezone: true }), createdAt: createdAt(),
}, (table) => [unique("uq_invitation_token_hash").on(table.tokenHash), unique("uq_invitation_passcode_hash").on(table.passcodeHash)]);

export const pointReservations = pgTable("point_reservation", { id: id(), accountId: text("account_id").notNull(), amount: integer("amount").notNull(), state: text("state").notNull().default("reserved"), purpose: text("purpose").notNull(), idempotencyKey: text("idempotency_key").notNull(), createdAt: createdAt(), updatedAt: timestamp("updated_at", { withTimezone: true }).defaultNow().notNull() });

export const pointAccounts = pgTable("point_account", {
	id: id(), ownerUserId: text("owner_user_id"), organizationId: text("organization_id"), createdAt: createdAt(),
}, (table) => [unique("uq_point_account_user").on(table.ownerUserId), unique("uq_point_account_organization").on(table.organizationId)]);

export const pointLedgerEntries = pgTable("point_ledger_entry", {
	id: id(), accountId: text("account_id").notNull(), amount: integer("amount").notNull(), reason: text("reason").notNull(), idempotencyKey: text("idempotency_key").notNull(), createdAt: createdAt(),
}, (table) => [unique("uq_point_ledger_entry_idempotency").on(table.accountId, table.idempotencyKey)]);

export const weeklyFreeUses = pgTable("weekly_free_use", {
	id: id(), userId: text("user_id").notNull(), weekStart: timestamp("week_start", { withTimezone: true }).notNull(), createdAt: createdAt(),
}, (table) => [unique("uq_weekly_free_use").on(table.userId, table.weekStart)]);

export const requirementAssessments = pgTable("requirement_assessment", {
	id: id(), evaluationId: text("evaluation_id").notNull(), jobRequirementId: text("job_requirement_id").notNull(), outcome: text("outcome").notNull(), confidence: integer("confidence").notNull(), reasoning: text("reasoning").notNull(), evidence: jsonb("evidence").notNull(), deterministicEvidence: jsonb("deterministic_evidence"), semanticEvidence: jsonb("semantic_evidence"), lexicalEvidence: jsonb("lexical_evidence"), createdAt: createdAt(),
}, (table) => [unique("uq_assessment_evaluation_requirement").on(table.evaluationId, table.jobRequirementId)]);

export const batchEvaluationSubmissions = pgTable("batch_evaluation_submission", {
	organizationId: text("organization_id").notNull(), jobId: text("job_id").notNull(), batchEvaluationId: text("batch_evaluation_id").notNull(), resumeSubmissionId: text("resume_submission_id").notNull(), createdAt: createdAt(),
}, (table) => [primaryKey({ columns: [table.batchEvaluationId, table.resumeSubmissionId] })]);

export const resumeBlockEmbeddings = pgTable("resume_block_embedding", { resumeVersionId: text("resume_version_id").notNull(), blockId: text("block_id").notNull(), model: text("model").notNull(), textHash: text("text_hash").notNull(), vector: jsonb("vector").notNull(), createdAt: createdAt() }, (table) => [primaryKey({ columns: [table.resumeVersionId, table.blockId, table.model] })]);

export type ProcessingJob = typeof processingJobs.$inferSelect;
