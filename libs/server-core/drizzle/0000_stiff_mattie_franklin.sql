CREATE TABLE "account" (
	"id" text PRIMARY KEY NOT NULL,
	"account_id" text NOT NULL,
	"provider_id" text NOT NULL,
	"user_id" text NOT NULL,
	"password" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_account_provider_account" UNIQUE("provider_id","account_id")
);
--> statement-breakpoint
CREATE TABLE "batch_evaluation_submission" (
	"organization_id" text NOT NULL,
	"job_id" text NOT NULL,
	"batch_evaluation_id" text NOT NULL,
	"resume_submission_id" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "batch_evaluation_submission_batch_evaluation_id_resume_submission_id_pk" PRIMARY KEY("batch_evaluation_id","resume_submission_id")
);
--> statement-breakpoint
CREATE TABLE "batch_evaluation" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"job_id" text NOT NULL,
	"job_version_id" text NOT NULL,
	"created_by_user_id" text NOT NULL,
	"requirement_schema_version" text NOT NULL,
	"scoring_policy_version" text NOT NULL,
	"model_configuration" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "candidate_record" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"user_id" text,
	"full_name" text,
	"email" text,
	"phone" text,
	"location" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "embedding_cache" (
	"text_hash" text PRIMARY KEY NOT NULL,
	"model" text NOT NULL,
	"vector" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "evaluation" (
	"id" text PRIMARY KEY NOT NULL,
	"batch_evaluation_id" text,
	"resume_submission_id" text NOT NULL,
	"job_version_id" text NOT NULL,
	"resume_version_id" text NOT NULL,
	"status" text DEFAULT 'pending' NOT NULL,
	"score" integer,
	"evidence_coverage" integer,
	"eligibility" text DEFAULT 'pending' NOT NULL,
	"quality_state" text DEFAULT 'pending' NOT NULL,
	"rank" integer,
	"point_reservation_id" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "independent_evaluation" (
	"id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"storage_key" text NOT NULL,
	"original_name" text NOT NULL,
	"media_type" text NOT NULL,
	"job_description" text,
	"job_description_key" text,
	"job_description_media_type" text,
	"status" text DEFAULT 'queued' NOT NULL,
	"score" integer,
	"suggestions" jsonb,
	"improved_resume_key" text,
	"normalized_facts" jsonb,
	"safe_error" text,
	"point_reservation_id" text,
	"free_week_start" timestamp with time zone,
	"retention_date" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"completed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "invitation" (
	"id" text PRIMARY KEY NOT NULL,
	"job_id" text NOT NULL,
	"creator_user_id" text NOT NULL,
	"token_hash" text NOT NULL,
	"passcode_hash" text,
	"expires_at" timestamp with time zone NOT NULL,
	"redeeming_user_id" text,
	"resume_submission_id" text,
	"revoked_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_invitation_token_hash" UNIQUE("token_hash"),
	CONSTRAINT "uq_invitation_passcode_hash" UNIQUE("passcode_hash")
);
--> statement-breakpoint
CREATE TABLE "job_requirement" (
	"id" text PRIMARY KEY NOT NULL,
	"job_version_id" text NOT NULL,
	"stable_id" text NOT NULL,
	"kind" text NOT NULL,
	"weight" integer NOT NULL,
	"normalized_text" text NOT NULL,
	"category" text DEFAULT 'other' NOT NULL,
	"source_modality" text DEFAULT 'unclear' NOT NULL,
	"assessability" text DEFAULT 'unclear' NOT NULL,
	"predicate" jsonb DEFAULT '{}'::jsonb NOT NULL,
	"aliases" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"source_evidence" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"confirmed_at" timestamp with time zone,
	CONSTRAINT "uq_job_requirement_stable_id" UNIQUE("job_version_id","stable_id")
);
--> statement-breakpoint
CREATE TABLE "job_version" (
	"id" text PRIMARY KEY NOT NULL,
	"job_id" text NOT NULL,
	"version" integer NOT NULL,
	"source_text" text,
	"normalized_text" text,
	"source_media_type" text NOT NULL,
	"source_storage_key" text,
	"draft_requirements" jsonb,
	"schema_version" text,
	"prompt_version" text NOT NULL,
	"compiler_version" text NOT NULL,
	"confirmed_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_job_version" UNIQUE("job_id","version")
);
--> statement-breakpoint
CREATE TABLE "job" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"title" text NOT NULL,
	"application_opens_at" timestamp with time zone,
	"application_closes_at" timestamp with time zone,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "organization_allowed_email" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"email" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_organization_allowed_email" UNIQUE("organization_id","email")
);
--> statement-breakpoint
CREATE TABLE "organization_email_domain" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"domain" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_organization_email_domain" UNIQUE("domain")
);
--> statement-breakpoint
CREATE TABLE "organization_entitlement" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"provisioned_by" text,
	"note" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_organization_entitlement" UNIQUE("organization_id")
);
--> statement-breakpoint
CREATE TABLE "organization_member" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"user_id" text NOT NULL,
	"role" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_organization_member" UNIQUE("organization_id","user_id"),
	CONSTRAINT "uq_organization_member_user" UNIQUE("user_id")
);
--> statement-breakpoint
CREATE TABLE "organization" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"default_member_role" text DEFAULT 'viewer' NOT NULL,
	"retention_days" integer DEFAULT 90 NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "point_account" (
	"id" text PRIMARY KEY NOT NULL,
	"owner_user_id" text,
	"organization_id" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_point_account_user" UNIQUE("owner_user_id"),
	CONSTRAINT "uq_point_account_organization" UNIQUE("organization_id")
);
--> statement-breakpoint
CREATE TABLE "point_ledger_entry" (
	"id" text PRIMARY KEY NOT NULL,
	"account_id" text NOT NULL,
	"amount" integer NOT NULL,
	"reason" text NOT NULL,
	"idempotency_key" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_point_ledger_entry_idempotency" UNIQUE("account_id","idempotency_key")
);
--> statement-breakpoint
CREATE TABLE "point_reservation" (
	"id" text PRIMARY KEY NOT NULL,
	"account_id" text NOT NULL,
	"amount" integer NOT NULL,
	"state" text DEFAULT 'reserved' NOT NULL,
	"purpose" text NOT NULL,
	"idempotency_key" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "processing_job" (
	"id" text PRIMARY KEY NOT NULL,
	"type" text NOT NULL,
	"status" text DEFAULT 'ready' NOT NULL,
	"payload_reference" text NOT NULL,
	"idempotency_key" text NOT NULL,
	"attempt_count" integer DEFAULT 0 NOT NULL,
	"maximum_attempts" integer DEFAULT 3 NOT NULL,
	"available_at" timestamp with time zone DEFAULT now() NOT NULL,
	"lease_token" text,
	"lease_expires_at" timestamp with time zone,
	"safe_error" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_processing_job_idempotency" UNIQUE("type","idempotency_key")
);
--> statement-breakpoint
CREATE TABLE "razorpay_order" (
	"id" text PRIMARY KEY NOT NULL,
	"razorpay_order_id" text NOT NULL,
	"account_id" text NOT NULL,
	"purchaser_user_id" text NOT NULL,
	"pack_id" text NOT NULL,
	"points" integer NOT NULL,
	"amount_inr" integer NOT NULL,
	"currency" text DEFAULT 'INR' NOT NULL,
	"status" text DEFAULT 'created' NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_razorpay_order_id" UNIQUE("razorpay_order_id")
);
--> statement-breakpoint
CREATE TABLE "razorpay_payment" (
	"id" text PRIMARY KEY NOT NULL,
	"razorpay_payment_id" text NOT NULL,
	"order_row_id" text NOT NULL,
	"status" text NOT NULL,
	"method" text,
	"amount_inr" integer NOT NULL,
	"refunded_inr" integer DEFAULT 0 NOT NULL,
	"points_granted" boolean DEFAULT false NOT NULL,
	"signature_verified" boolean DEFAULT false NOT NULL,
	"source" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_razorpay_payment_id" UNIQUE("razorpay_payment_id")
);
--> statement-breakpoint
CREATE TABLE "razorpay_webhook_event" (
	"id" text PRIMARY KEY NOT NULL,
	"event_type" text NOT NULL,
	"payload" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"processed_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "requirement_assessment" (
	"id" text PRIMARY KEY NOT NULL,
	"evaluation_id" text NOT NULL,
	"job_requirement_id" text NOT NULL,
	"outcome" text NOT NULL,
	"confidence" integer NOT NULL,
	"reasoning" text NOT NULL,
	"evidence" jsonb NOT NULL,
	"deterministic_evidence" jsonb,
	"semantic_evidence" jsonb,
	"lexical_evidence" jsonb,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_assessment_evaluation_requirement" UNIQUE("evaluation_id","job_requirement_id")
);
--> statement-breakpoint
CREATE TABLE "resume_block_embedding" (
	"resume_version_id" text NOT NULL,
	"block_id" text NOT NULL,
	"model" text NOT NULL,
	"text_hash" text NOT NULL,
	"vector" jsonb NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "resume_block_embedding_resume_version_id_block_id_model_pk" PRIMARY KEY("resume_version_id","block_id","model")
);
--> statement-breakpoint
CREATE TABLE "resume_document" (
	"id" text PRIMARY KEY NOT NULL,
	"owner_user_id" text,
	"organization_id" text,
	"candidate_record_id" text,
	"storage_key" text NOT NULL,
	"checksum" text NOT NULL,
	"media_type" text NOT NULL,
	"size_bytes" integer NOT NULL,
	"original_name" text NOT NULL,
	"retention_date" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "resume_submission" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"job_id" text NOT NULL,
	"candidate_record_id" text NOT NULL,
	"resume_version_id" text NOT NULL,
	"submitting_user_id" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "resume_version" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text,
	"resume_document_id" text NOT NULL,
	"version" integer NOT NULL,
	"extraction_blocks" jsonb,
	"structured_facts" jsonb,
	"normalized_facts" jsonb,
	"quality_state" text DEFAULT 'pending' NOT NULL,
	"parser_version" text,
	"parser_configuration_version" text,
	"schema_version" text,
	"extraction_prompt_version" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_resume_version" UNIQUE("resume_document_id","version")
);
--> statement-breakpoint
CREATE TABLE "review_decision" (
	"id" text PRIMARY KEY NOT NULL,
	"organization_id" text NOT NULL,
	"batch_evaluation_id" text NOT NULL,
	"evaluation_id" text NOT NULL,
	"reviewer_user_id" text NOT NULL,
	"eligibility" text NOT NULL,
	"reason" text NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "user" (
	"id" text PRIMARY KEY NOT NULL,
	"name" text NOT NULL,
	"email" text NOT NULL,
	"account_type" text DEFAULT 'candidate' NOT NULL,
	"email_verified" boolean DEFAULT false NOT NULL,
	"is_demo" boolean DEFAULT false NOT NULL,
	"image" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_user_email" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "weekly_free_use" (
	"id" text PRIMARY KEY NOT NULL,
	"user_id" text NOT NULL,
	"week_start" timestamp with time zone NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "uq_weekly_free_use" UNIQUE("user_id","week_start")
);
