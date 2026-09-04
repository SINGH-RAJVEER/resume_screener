import { zValidator } from "@hono/zod-validator";
import { Hono } from "hono";
import { cors } from "hono/cors";
import { and, desc, eq, sql } from "drizzle-orm";
import { z } from "zod";
import { createDatabase, type Database } from "@skillsignal/server-core/db";
import { loadConfig, type ServerConfig } from "@skillsignal/server-core/config";
import { loadBillingSettings } from "@skillsignal/server-core/billing";
import { availableBalance, balance, ensureOrganizationAccount, ensureUserAccount, grantInSession, releaseInSession, reserveInSession, InsufficientPointsError } from "@skillsignal/server-core/points";
import { purgeExpiredData } from "@skillsignal/server-core/retention";
import { LocalObjectStorage } from "@skillsignal/server-core/storage";
import { SCORING_POLICY_VERSION } from "@skillsignal/server-core/versions";
import { batchEvaluations, candidateRecords, evaluations, independentEvaluations, invitations, jobRequirements, jobVersions, jobs, organizationAllowedEmails, organizationEmailDomains, organizationMembers, organizations, processingJobs, resumeDocuments, resumeSubmissions, resumeVersions, users, weeklyFreeUses } from "@skillsignal/server-core/schema";
import { authenticate, issueToken, register, signIn, type AuthUser } from "./auth.ts";
import { mkdir } from "node:fs/promises";
import { join, resolve } from "node:path";
import { createHash, timingSafeEqual } from "node:crypto";
import { unzipSync } from "fflate";
import { RazorpayClient, RazorpayError, RazorpayUnavailableError, verifyCheckoutSignature, verifyWebhookSignature, paymentEntity } from "./billing/razorpay.ts";
import { EMPLOYER_QUOTE, INDEPENDENT_QUOTE, UnknownQuoteKindError, pointQuote } from "./billing/quotes.ts";
import { claimFreeWeek, nextReset, weekStart } from "./billing/allowance.ts";

type Variables = { user: AuthUser };
export type ApiApp = Hono<{ Variables: Variables }>;

const credentials = z.object({ name: z.string().trim().min(1).max(100), email: z.string().email().max(254), password: z.string().min(8).max(72) });
const signInBody = credentials.pick({ email: true, password: true });
const requirement = z.object({ stableId: z.string().min(1), normalizedText: z.string().min(1), kind: z.enum(["required", "preferred", "ignored", "hard_gate"]), weight: z.number().int().positive() });
const responseUser = (user: AuthUser) => ({ id: user.id, name: user.name, email: user.email, accountType: user.accountType, emailVerified: user.emailVerified, image: user.image, createdAt: user.createdAt, updatedAt: user.updatedAt });
const error = (code: string, message: string, status: 400 | 401 | 402 | 403 | 404 | 409 | 500 | 502 | 503 = 400) => new Response(JSON.stringify({ code, message }), { status, headers: { "Content-Type": "application/json" } });

const authResponse = async (user: AuthUser, config: ServerConfig) => {
	const issued = await issueToken(user, config.jwtSecret, config.jwtTtlSeconds);
	return { user: responseUser(user), token: issued.token, tokenType: "Bearer", expiresAt: issued.expiresAt };
};

const mediaTypes: Record<string, { mediaType: string; extension: string }> = {
	".pdf": { mediaType: "application/pdf", extension: ".pdf" },
	".docx": { mediaType: "application/vnd.openxmlformats-officedocument.wordprocessingml.document", extension: ".docx" },
	".txt": { mediaType: "text/plain", extension: ".txt" },
};

const validateUpload = (file: File): { mediaType: string; extension: string } => {
	const extension = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
	const expected = mediaTypes[extension];
	if (!expected || file.size === 0 || file.size > 20 * 1024 * 1024) throw new Error("Document must be a PDF, DOCX, or TXT file between 1 byte and 20 MB");
	if (file.type && file.type !== expected.mediaType) throw new Error("Document filename does not match its media type");
	return expected;
};

const persistObject = async (root: string, key: string, content: Uint8Array): Promise<void> => {
	const base = resolve(root);
	const target = resolve(join(base, key));
	if (!target.startsWith(`${base}/`)) throw new Error("Storage key escapes the configured root");
	await mkdir(join(target, ".."), { recursive: true });
	await Bun.write(target, content);
};

const digest = (value: string): string => createHash("sha256").update(value).digest("hex");
const randomPasscode = (): string => Array.from({ length: 8 }, () => "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"[Math.floor(Math.random() * 32)]).join("");

const OUTCOME_VALUES: Record<string, number> = { met: 1, partial: 0.5, not_met: 0 };
const VALID_EVALUATION_STATUSES = new Set(["pending", "processing", "complete", "failed"]);
const VALID_ASSESSMENT_OUTCOMES = new Set(["met", "partial", "not_met", "unknown"]);
const EXPORT_COLUMNS: Record<string, string> = {
	candidate_name: "candidate_name", candidate_email: "candidate_email", candidate_location: "candidate_location",
	status: "status", score: "score", eligibility: "eligibility", evidence_coverage: "evidence_coverage",
	quality_state: "quality_state", quality_warnings: "quality_warnings",
};

const contributionByIndex = (assessments: Array<{ outcome: string; kind: string; weight: number }>): Array<number | null> => {
	const confidentWeight = assessments.filter((item) => item.kind !== "hard_gate" && item.outcome in OUTCOME_VALUES).reduce((sum, item) => sum + item.weight, 0);
	return assessments.map((item) => {
		const value = OUTCOME_VALUES[item.outcome];
		return value === undefined || item.kind === "hard_gate" || !confidentWeight ? null : Math.round(value * item.weight / confidentWeight * 1000) / 10;
	});
};

const csvSafe = (value: unknown): string => {
	const text = String(value ?? "");
	return ["=", "+", "-", "@", "\t", "\r"].some((prefix) => text.startsWith(prefix)) ? `'${text}` : text;
};

const escapeCsvCell = (value: unknown): string => {
	const text = csvSafe(value);
	return /[",\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
};

const skillNamesFromFacts = (facts: unknown): string[] => {
	if (typeof facts !== "object" || facts === null) return [];
	const skills = (facts as Record<string, unknown>)["skills"];
	if (!Array.isArray(skills)) return [];
	const names = new Set<string>();
	for (const skill of skills) {
		if (typeof skill === "object" && skill !== null) {
			const name = (skill as Record<string, unknown>)["canonicalName"];
			if (typeof name === "string" && name.trim()) names.add(name.trim());
		}
	}
	return [...names].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase()));
};

const qualityFromVersion = (version: { qualityState: string; extractionBlocks: unknown; normalizedFacts: unknown }): { qualityState: string; qualityWarnings: string[] } => {
	const blocks = (version.extractionBlocks ?? {}) as Record<string, unknown>;
	const quality = (blocks["quality"] ?? {}) as Record<string, unknown>;
	const normalized = (version.normalizedFacts ?? {}) as Record<string, unknown>;
	const rawWarnings = Array.isArray(normalized["warnings"]) ? normalized["warnings"] : Array.isArray(quality["warnings"]) ? quality["warnings"] : [];
	return { qualityState: version.qualityState, qualityWarnings: [...new Set((rawWarnings as unknown[]).filter((item): item is string => typeof item === "string"))] };
};

const isAdmin = (c: { req: { header: (name: string) => string | undefined } }): boolean => {
	const token = c.req.header("x-admin-token") ?? "";
	const expected = Bun.env["ADMIN_TOKEN"] ?? "";
	return Boolean(expected) && token.length === expected.length && timingSafeEqual(Buffer.from(token), Buffer.from(expected));
};

type BillingOrder = { id: string; account_id: string; pack_id: string; points: number; amount_inr: number };

const grantForCaptured = async (db: Database, order: BillingOrder, paymentId: string, status: string): Promise<boolean> => {
	if (status !== "captured" && status !== "authorized") return false;
	const payment = (await db.execute(sql`SELECT points_granted FROM razorpay_payment WHERE razorpay_payment_id = ${paymentId}`))[0] as { points_granted: boolean } | undefined;
	if (!payment || payment.points_granted) return false;
	await grantInSession(db, order.account_id, order.points, `Razorpay purchase ${order.pack_id}`, `purchase:${paymentId}`);
	await db.execute(sql`UPDATE razorpay_payment SET points_granted = true, updated_at = now() WHERE razorpay_payment_id = ${paymentId}`);
	await db.execute(sql`UPDATE razorpay_order SET status = 'paid', updated_at = now() WHERE id = ${order.id}`);
	return true;
};

const syncRefunds = async (db: Database, order: BillingOrder, payment: Record<string, unknown>): Promise<number> => {
	const refunds = payment["refunds"];
	if (!Array.isArray(refunds)) return 0;
	let total = 0;
	for (const refund of refunds) {
		if (typeof refund !== "object" || refund === null) continue;
		const entry = refund as Record<string, unknown>;
		const refundId = String(entry["id"] ?? "");
		const amountPaise = entry["amount"];
		if (!refundId || typeof amountPaise !== "number") continue;
		const existing = (await db.execute(sql`SELECT id FROM point_ledger_entry WHERE account_id = ${order.account_id} AND idempotency_key = ${`refund:${refundId}`}`))[0];
		if (existing) continue;
		const amountInr = Math.floor(amountPaise / 100);
		const pointsBack = Math.ceil(order.points * amountInr / order.amount_inr);
		await db.execute(sql`INSERT INTO point_ledger_entry (id, account_id, amount, reason, idempotency_key, created_at) VALUES (${crypto.randomUUID()}, ${order.account_id}, ${-pointsBack}, ${`Razorpay refund ${order.pack_id}`}, ${`refund:${refundId}`}, now())`);
		total += amountInr;
	}
	if (total) {
		await db.execute(sql`UPDATE razorpay_payment SET refunded_inr = refunded_inr + ${total}, updated_at = now() WHERE order_row_id = ${order.id} AND razorpay_payment_id = ${String(payment["id"] ?? "")}`);
		const paid = (await db.execute(sql`SELECT refunded_inr FROM razorpay_payment WHERE order_row_id = ${order.id} AND razorpay_payment_id = ${String(payment["id"] ?? "")}`))[0] as { refunded_inr: number } | undefined;
		if (paid && paid.refunded_inr >= order.amount_inr) await db.execute(sql`UPDATE razorpay_order SET status = 'refunded', updated_at = now() WHERE id = ${order.id}`);
	}
	return total;
};

export const createApp = (db: Database, config: ServerConfig): ApiApp => {
	const app: ApiApp = new Hono();
	app.use("*", cors({ origin: config.webUrl, allowHeaders: ["Content-Type", "Authorization", "Idempotency-Key"], allowMethods: ["GET", "POST", "PUT", "DELETE", "OPTIONS"] }));
	app.onError((err, c) => {
		console.error("unhandled request error", { name: err.name });
		return c.json({ code: "INTERNAL_ERROR", message: "Internal server error" }, 500);
	});
	app.use("/api/*", async (c, next) => {
		const authorization = c.req.header("Authorization");
		if (authorization?.startsWith("Bearer ")) {
			const user = await authenticate(db, authorization.slice(7), config.jwtSecret);
			if (user) c.set("user", user);
		}
		await next();
	});
	const requireUser = (c: import("hono").Context<{ Variables: Variables }>) => {
		const user = c.get("user");
		return user ?? null;
	};

	app.get("/health", (c) => c.json({ status: "ok" }));
	app.post("/api/auth/sign-up/email", zValidator("json", credentials), async (c) => {
		const body = c.req.valid("json");
		try { return c.json(await authResponse(await register(db, body.name, body.email, body.password, "candidate"), config), 201); } catch (cause) { if (String(cause).includes("uq_user_email")) return error("EMAIL_ALREADY_EXISTS", "Email is already registered", 409); throw cause; }
	});
	app.post("/api/employer/auth/sign-up/email", zValidator("json", credentials), async (c) => {
		const body = c.req.valid("json");
		try { return c.json(await authResponse(await register(db, body.name, body.email, body.password, "employer"), config), 201); } catch (cause) { if (String(cause).includes("uq_user_email")) return error("EMAIL_ALREADY_EXISTS", "Email is already registered", 409); throw cause; }
	});
	app.post("/api/auth/sign-in/email", zValidator("json", signInBody), async (c) => { const body = c.req.valid("json"); const user = await signIn(db, body.email, body.password, "candidate"); return user ? c.json(await authResponse(user, config)) : error("INVALID_EMAIL_OR_PASSWORD", "Invalid email or password", 401); });
	app.post("/api/employer/auth/sign-in/email", zValidator("json", signInBody), async (c) => { const body = c.req.valid("json"); const user = await signIn(db, body.email, body.password, "employer"); return user ? c.json(await authResponse(user, config)) : error("INVALID_EMAIL_OR_PASSWORD", "Invalid email or password", 401); });
	app.post("/api/auth/sign-out", (c) => c.json({ success: true }));
	app.get("/api/auth/session", (c) => { const user = requireUser(c); return c.json(user ? { user: responseUser(user) } : null); });
	app.get("/api/me", (c) => { const user = requireUser(c); return user ? c.json({ user: responseUser(user) }) : error("UNAUTHORIZED", "Unauthorized", 401); });

	app.get("/api/organizations", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		return c.json(await db.select({ id: organizations.id, name: organizations.name, role: organizationMembers.role }).from(organizationMembers).innerJoin(organizations, eq(organizations.id, organizationMembers.organizationId)).where(eq(organizationMembers.userId, user.id)));
	});
	app.post("/api/organizations", zValidator("json", z.object({ name: z.string().trim().min(1).max(200) })), async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401);
		const body = c.req.valid("json");
		const organizationId = crypto.randomUUID();
		const result = await db.transaction(async (tx) => { const organization = (await tx.insert(organizations).values({ id: organizationId, name: body.name }).returning())[0]; await tx.insert(organizationMembers).values({ id: crypto.randomUUID(), organizationId, userId: user.id, role: "owner" }); return organization; });
		return c.json(result, 201);
	});

	app.get("/api/organizations/:organizationId/jobs", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.param("organizationId");
		const membership = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!membership[0]) return error("NOT_FOUND", "Organization not found", 404);
		const rows = await db.select({ job: jobs, version: jobVersions }).from(jobs).innerJoin(jobVersions, eq(jobVersions.jobId, jobs.id)).where(eq(jobs.organizationId, organizationId)).orderBy(desc(jobs.createdAt), desc(jobVersions.version));
		const latest = new Map<string, (typeof rows)[number]>();
		for (const row of rows) if (!latest.has(row.job.id)) latest.set(row.job.id, row);
		return c.json([...latest.values()].map(({ job, version }) => ({ id: job.id, title: job.title, versionId: version.id, confirmed: version.confirmedAt !== null })));
	});

	app.post("/api/jobs", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401);
		const body = await c.req.parseBody();
		const organizationId = String(body["organization_id"] ?? "");
		const title = String(body["title"] ?? "").trim();
		const description = String(body["description"] ?? "").trim();
		const file = body["file"] instanceof File ? body["file"] : null;
		if (!organizationId || !title || (!description && !file) || (description && file)) return error("INVALID_REQUEST", "Provide a title and either a pasted description or a file", 400);
		const membership = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!membership[0] || !["owner", "recruiter"].includes(membership[0].role)) return error("FORBIDDEN", "Recruiter access required", 403);
		let sourceStorageKey: string | null = null;
		let sourceText: string | null = description || null;
		let sourceMediaType = "text/plain";
		let content: Uint8Array | null = null;
		if (file) { try { const media = validateUpload(file); sourceMediaType = media.mediaType; sourceStorageKey = `job-descriptions/${crypto.randomUUID()}${media.extension}`; content = new Uint8Array(await file.arrayBuffer()); } catch (cause) { return error("INVALID_DOCUMENT", cause instanceof Error ? cause.message : "Invalid document", 400); } }
		const jobId = crypto.randomUUID();
		const versionId = crypto.randomUUID();
		const processingId = crypto.randomUUID();
		await db.transaction(async (tx) => {
			await tx.insert(jobs).values({ id: jobId, organizationId, title });
			await tx.insert(jobVersions).values({ id: versionId, jobId, version: 1, sourceText, normalizedText: sourceText, sourceMediaType, sourceStorageKey, promptVersion: "pending-ts-port", compilerVersion: "pending-ts-port" });
			await tx.insert(processingJobs).values({ id: processingId, type: "job_description_processing", payloadReference: versionId, idempotencyKey: versionId });
		});
		if (sourceStorageKey && content) await persistObject(config.storageRoot, sourceStorageKey, content);
		return c.json({ id: jobId, versionId, processingJobId: processingId }, 202);
	});

	app.get("/api/jobs/:jobId", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const jobId = c.req.param("jobId");
		const jobResult = await db.select({ job: jobs, version: jobVersions }).from(jobs).innerJoin(jobVersions, eq(jobVersions.jobId, jobs.id)).where(eq(jobs.id, jobId)).orderBy(desc(jobVersions.version)).limit(1);
		const row = jobResult[0]; if (!row) return error("NOT_FOUND", "Job not found", 404);
		const membership = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, row.job.organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!membership[0]) return error("NOT_FOUND", "Job not found", 404);
		const requirements = await db.select().from(jobRequirements).where(eq(jobRequirements.jobVersionId, row.version.id));
		return c.json({ id: row.job.id, organizationId: row.job.organizationId, title: row.job.title, applicationOpensAt: row.job.applicationOpensAt, applicationClosesAt: row.job.applicationClosesAt, description: row.version.sourceText, confirmed: row.version.confirmedAt !== null, draftStatus: row.version.draftRequirements ? "ready" : "processing", draftRequirements: (row.version.draftRequirements as { requirements?: unknown[] } | null)?.requirements ?? [], requirements: requirements.map((item) => ({ id: item.id, stableId: item.stableId, text: item.normalizedText, kind: item.kind, weight: item.weight, category: item.category, sourceModality: item.sourceModality, assessability: item.assessability, predicate: item.predicate, sourceEvidence: item.sourceEvidence })) });
	});

	app.post("/api/jobs/:jobId/requirements", zValidator("json", z.object({ requirements: z.array(requirement) })), async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401);
		const jobId = c.req.param("jobId"); const input = c.req.valid("json");
		const result = await db.select({ job: jobs, version: jobVersions }).from(jobs).innerJoin(jobVersions, eq(jobVersions.jobId, jobs.id)).where(eq(jobs.id, jobId)).orderBy(desc(jobVersions.version)).limit(1);
		const current = result[0]; if (!current) return error("NOT_FOUND", "Job not found", 404);
		const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, current.job.organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!member[0] || !["owner", "recruiter"].includes(member[0].role)) return error("FORBIDDEN", "Recruiter access required", 403);
		const versionId = crypto.randomUUID();
		await db.transaction(async (tx) => {
			await tx.insert(jobVersions).values({ id: versionId, jobId, version: current.version.version + 1, sourceText: current.version.sourceText, normalizedText: current.version.normalizedText, sourceMediaType: current.version.sourceMediaType, sourceStorageKey: current.version.sourceStorageKey, draftRequirements: current.version.draftRequirements, schemaVersion: current.version.schemaVersion, promptVersion: current.version.promptVersion, compilerVersion: current.version.compilerVersion, confirmedAt: new Date() });
			await tx.insert(jobRequirements).values(input.requirements.map((item) => ({ id: crypto.randomUUID(), jobVersionId: versionId, stableId: item.stableId, normalizedText: item.normalizedText, kind: item.kind, weight: item.weight, sourceEvidence: [], predicate: {}, aliases: [], assessability: "resume_evidence", confirmedAt: new Date() })));
		});
		return c.json({ confirmed: true }, 201);
	});

	app.post("/api/jobs/:jobId/resumes", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const body = await c.req.parseBody(); const file = body["file"] instanceof File ? body["file"] : null; const invitationValue = typeof body["invitation_token"] === "string" ? body["invitation_token"] : "";
		if (!file) return error("INVALID_REQUEST", "A resume file is required", 400);
		let media: { mediaType: string; extension: string };
		try { media = validateUpload(file); } catch (cause) { return error("INVALID_DOCUMENT", cause instanceof Error ? cause.message : "Invalid document", 400); }
		const jobId = c.req.param("jobId");
		const result = await db.select({ job: jobs, version: jobVersions }).from(jobs).innerJoin(jobVersions, eq(jobVersions.jobId, jobs.id)).where(eq(jobs.id, jobId)).orderBy(desc(jobVersions.version)).limit(1);
		const current = result[0]; if (!current) return error("NOT_FOUND", "Job not found", 404);
		let invitationId: string | null = null;
		if (invitationValue) {
			if (user.accountType !== "candidate") return error("FORBIDDEN", "Candidate account required", 403);
			const invitation = (await db.select().from(invitations).where(eq(invitations.tokenHash, digest(invitationValue))).limit(1))[0] ?? (await db.select().from(invitations).where(eq(invitations.passcodeHash, digest(invitationValue.trim().toUpperCase()))).limit(1))[0];
			if (!invitation || invitation.jobId !== jobId || invitation.redeemingUserId !== user.id || invitation.revokedAt || invitation.resumeSubmissionId || invitation.expiresAt <= new Date()) return error("NOT_FOUND", "Invitation is unavailable", 404);
			invitationId = invitation.id;
		} else {
			if (user.accountType !== "employer") return error("FORBIDDEN", "Employer access required", 403);
			const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, current.job.organizationId), eq(organizationMembers.userId, user.id))).limit(1);
			if (!member[0] || !["owner", "recruiter"].includes(member[0].role)) return error("FORBIDDEN", "Recruiter access required", 403);
		}
		if (!current.version.confirmedAt) return error("REQUIREMENTS_NOT_CONFIRMED", "Job requirements must be confirmed", 409);
		if (invitationId && (!current.job.applicationOpensAt || !current.job.applicationClosesAt || current.job.applicationOpensAt > new Date() || current.job.applicationClosesAt <= new Date())) return error("APPLICATIONS_CLOSED", "Job applications are not open", 409);
		let employerQuote;
		try { employerQuote = pointQuote(EMPLOYER_QUOTE, loadBillingSettings()); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
		const entitlement = (await db.execute(sql`SELECT id FROM organization_entitlement WHERE organization_id = ${current.job.organizationId} LIMIT 1`))[0];
		const orgAccount = await ensureOrganizationAccount(db, current.job.organizationId);
		const candidateId = crypto.randomUUID(); const documentId = crypto.randomUUID(); const versionId = crypto.randomUUID(); const submissionId = crypto.randomUUID(); const batchId = crypto.randomUUID(); const evaluationId = crypto.randomUUID(); const processingId = crypto.randomUUID();
		let employerReservationId: string | null = null;
		if (!entitlement) {
			try {
				const reservation = await reserveInSession(db, orgAccount.id, employerQuote.points, "employer_resume", `employer-resume:${evaluationId}`);
				employerReservationId = reservation.id;
			} catch (cause) {
				if (cause instanceof InsufficientPointsError) return error("INSUFFICIENT_POINTS", `This evaluation requires up to ${employerQuote.points} points`, 402);
				throw cause;
			}
		}
		const content = new Uint8Array(await file.arrayBuffer()); const storageKey = `resumes/${crypto.randomUUID()}${media.extension}`;
		await db.transaction(async (tx) => {
			await tx.insert(batchEvaluations).values({ id: batchId, organizationId: current.job.organizationId, jobId, jobVersionId: current.version.id, createdByUserId: user.id, requirementSchemaVersion: current.version.schemaVersion ?? "2", scoringPolicyVersion: SCORING_POLICY_VERSION });
			await tx.insert(candidateRecords).values({ id: candidateId, organizationId: current.job.organizationId, userId: invitationId ? user.id : null });
			await tx.insert(resumeDocuments).values({ id: documentId, organizationId: current.job.organizationId, candidateRecordId: candidateId, storageKey, checksum: createHash("sha256").update(content).digest("hex"), mediaType: media.mediaType, sizeBytes: content.byteLength, originalName: file.name, retentionDate: new Date(Date.now() + 90 * 86400000) });
			await tx.insert(resumeVersions).values({ id: versionId, organizationId: current.job.organizationId, resumeDocumentId: documentId, version: 1 });
			await tx.insert(resumeSubmissions).values({ id: submissionId, organizationId: current.job.organizationId, jobId, candidateRecordId: candidateId, resumeVersionId: versionId, submittingUserId: user.id });
			await tx.insert(evaluations).values({ id: evaluationId, batchEvaluationId: batchId, resumeSubmissionId: submissionId, jobVersionId: current.version.id, resumeVersionId: versionId, pointReservationId: employerReservationId });
			await tx.execute(sql`INSERT INTO batch_evaluation_submission (organization_id, job_id, batch_evaluation_id, resume_submission_id, created_at) VALUES (${current.job.organizationId}, ${jobId}, ${batchId}, ${submissionId}, now())`);
			await tx.insert(processingJobs).values({ id: processingId, type: "resume_processing", payloadReference: versionId, idempotencyKey: versionId });
		});
		await persistObject(config.storageRoot, storageKey, content);
		if (invitationId) await db.update(invitations).set({ resumeSubmissionId: submissionId }).where(eq(invitations.id, invitationId));
		return c.json({ processingJobId: processingId, submissionId, evaluationId, batchEvaluationId: batchId }, 202);
	});

	app.post("/api/jobs/:jobId/resume-batches/files", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401);
		const body = await c.req.parseBody(); const files = Object.values(body).flatMap((value) => Array.isArray(value) ? value : [value]).filter((value): value is File => value instanceof File); if (!files.length || files.length > 500) return error("INVALID_REQUEST", "Batch must contain between 1 and 500 files", 400);
		const job = (await db.select({ job: jobs, version: jobVersions }).from(jobs).innerJoin(jobVersions, eq(jobVersions.jobId, jobs.id)).where(eq(jobs.id, c.req.param("jobId"))).orderBy(desc(jobVersions.version)).limit(1))[0]; if (!job) return error("NOT_FOUND", "Job not found", 404); if (!job.version.confirmedAt) return error("REQUIREMENTS_NOT_CONFIRMED", "Job requirements must be confirmed", 409);
		const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, job.job.organizationId), eq(organizationMembers.userId, user.id))).limit(1); if (!member[0] || !["owner", "recruiter"].includes(member[0].role)) return error("FORBIDDEN", "Recruiter access required", 403);
		const batchId = crypto.randomUUID(); await db.insert(batchEvaluations).values({ id: batchId, organizationId: job.job.organizationId, jobId: job.job.id, jobVersionId: job.version.id, createdByUserId: user.id, requirementSchemaVersion: job.version.schemaVersion ?? "2", scoringPolicyVersion: SCORING_POLICY_VERSION });
		let employerQuote;
		try { employerQuote = pointQuote(EMPLOYER_QUOTE, loadBillingSettings()); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
		const entitlement = (await db.execute(sql`SELECT id FROM organization_entitlement WHERE organization_id = ${job.job.organizationId} LIMIT 1`))[0];
		const orgAccount = await ensureOrganizationAccount(db, job.job.organizationId);
		const accepted: Array<Record<string, string>> = []; const rejected: Array<Record<string, string>> = [];
		for (const file of files) {
			try {
				const media = validateUpload(file); const content = new Uint8Array(await file.arrayBuffer()); const candidateId = crypto.randomUUID(); const documentId = crypto.randomUUID(); const versionId = crypto.randomUUID(); const submissionId = crypto.randomUUID(); const evaluationId = crypto.randomUUID(); const processingId = crypto.randomUUID(); const storageKey = `resumes/${crypto.randomUUID()}${media.extension}`;
				let reservationId: string | null = null;
				if (!entitlement) {
					try {
						reservationId = (await reserveInSession(db, orgAccount.id, employerQuote.points, "employer_resume", `employer-resume:${evaluationId}`)).id;
					} catch (cause) {
						if (cause instanceof InsufficientPointsError) { rejected.push({ name: file.name, reason: `This evaluation requires up to ${employerQuote.points} points` }); continue; }
						throw cause;
					}
				}
				await db.transaction(async (tx) => { await tx.insert(candidateRecords).values({ id: candidateId, organizationId: job.job.organizationId }); await tx.insert(resumeDocuments).values({ id: documentId, organizationId: job.job.organizationId, candidateRecordId: candidateId, storageKey, checksum: createHash("sha256").update(content).digest("hex"), mediaType: media.mediaType, sizeBytes: content.byteLength, originalName: file.name, retentionDate: new Date(Date.now() + 90 * 86400000) }); await tx.insert(resumeVersions).values({ id: versionId, organizationId: job.job.organizationId, resumeDocumentId: documentId, version: 1 }); await tx.insert(resumeSubmissions).values({ id: submissionId, organizationId: job.job.organizationId, jobId: job.job.id, candidateRecordId: candidateId, resumeVersionId: versionId, submittingUserId: user.id }); await tx.insert(evaluations).values({ id: evaluationId, batchEvaluationId: batchId, resumeSubmissionId: submissionId, jobVersionId: job.version.id, resumeVersionId: versionId, pointReservationId: reservationId }); await tx.execute(sql`INSERT INTO batch_evaluation_submission (organization_id, job_id, batch_evaluation_id, resume_submission_id, created_at) VALUES (${job.job.organizationId}, ${job.job.id}, ${batchId}, ${submissionId}, now())`); await tx.insert(processingJobs).values({ id: processingId, type: "resume_processing", payloadReference: versionId, idempotencyKey: versionId }); });
				await persistObject(config.storageRoot, storageKey, content); accepted.push({ name: file.name, processingJobId: processingId, submissionId, evaluationId });
			} catch (cause) { rejected.push({ name: file.name, reason: cause instanceof Error ? cause.message : "Invalid document" }); }
		}
		return c.json({ batchEvaluationId: accepted.length ? batchId : null, accepted, rejected }, 202);
	});

	app.post("/api/jobs/:jobId/resume-batches", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401); const body = await c.req.parseBody(); const archive = body["archive"] instanceof File ? body["archive"] : null; if (!archive) return error("INVALID_REQUEST", "A ZIP archive is required", 400);
		let files: File[] = []; try { const entries = unzipSync(new Uint8Array(await archive.arrayBuffer())); for (const [name, bytes] of Object.entries(entries)) { if (!name || name.endsWith("/") || name.includes("..") || name.startsWith("/") || name.toLowerCase().endsWith(".zip")) continue; files.push(new File([bytes], name, { type: mediaTypes[name.slice(name.lastIndexOf(".")).toLowerCase()]?.mediaType ?? "application/octet-stream" })); } } catch { return error("INVALID_DOCUMENT", "Resume ZIP file is malformed", 400); }
		const forwarded = new FormData(); for (const file of files) forwarded.append("files", file, file.name); const request = new Request(c.req.raw.url.replace(/\/resume-batches$/, "/resume-batches/files"), { method: "POST", headers: { Authorization: c.req.header("Authorization") ?? "", Origin: c.req.header("Origin") ?? "" }, body: forwarded }); return app.fetch(request);
	});

	app.post("/api/jobs/:jobId/invitations", zValidator("json", z.object({ expiresInHours: z.number().int().min(1).max(720).default(168) })), async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401);
		const job = (await db.select().from(jobs).where(eq(jobs.id, c.req.param("jobId"))).limit(1))[0]; if (!job) return error("NOT_FOUND", "Job not found", 404);
		const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, job.organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!member[0] || !["owner", "recruiter"].includes(member[0].role)) return error("FORBIDDEN", "Recruiter access required", 403);
		if (!job.applicationOpensAt || !job.applicationClosesAt || job.applicationOpensAt > new Date() || job.applicationClosesAt <= new Date()) return error("APPLICATIONS_CLOSED", "Job applications are not open", 409);
		const token = crypto.randomUUID().replaceAll("-", "") + crypto.randomUUID().replaceAll("-", ""); const passcode = randomPasscode(); const expiresAt = new Date(Date.now() + c.req.valid("json").expiresInHours * 3600000); const id = crypto.randomUUID();
		await db.insert(invitations).values({ id, jobId: job.id, creatorUserId: user.id, tokenHash: digest(token), passcodeHash: digest(passcode), expiresAt });
		return c.json({ id, token, passcode, expiresAt }, 201);
	});

	app.post("/api/independent-evaluations", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "candidate") return error("UNAUTHORIZED", "Candidate access required", 401);
		const body = await c.req.parseBody();
		const file = body["file"] instanceof File ? body["file"] : null;
		if (!file) return error("INVALID_REQUEST", "A resume file is required", 400);
		let media: { mediaType: string; extension: string };
		try { media = validateUpload(file); } catch (cause) { return error("INVALID_DOCUMENT", cause instanceof Error ? cause.message : "Invalid document", 400); }
		const jobDescriptionFile = body["job_description_file"] instanceof File ? body["job_description_file"] : null;
		const pastedDescription = typeof body["job_description"] === "string" ? body["job_description"].trim() : "";
		if (jobDescriptionFile && pastedDescription) return error("INVALID_REQUEST", "Provide either a pasted description or a file, not both", 400);
		if (pastedDescription.length > 100000) return error("INVALID_REQUEST", "Job description must be at most 100,000 characters", 400);
		let jobDescriptionKey: string | null = null;
		let jobDescriptionMediaType: string | null = null;
		let jobDescriptionContent: Uint8Array | null = null;
		if (jobDescriptionFile) {
			try {
				const described = validateUpload(jobDescriptionFile);
				jobDescriptionMediaType = described.mediaType;
				jobDescriptionKey = `independent-job-descriptions/${crypto.randomUUID()}${described.extension}`;
				jobDescriptionContent = new Uint8Array(await jobDescriptionFile.arrayBuffer());
			} catch (cause) { return error("INVALID_DOCUMENT", cause instanceof Error ? cause.message : "Invalid document", 400); }
		}
		const content = new Uint8Array(await file.arrayBuffer());
		const id = crypto.randomUUID();
		const processingId = crypto.randomUUID();
		const storageKey = `independent-resumes/${crypto.randomUUID()}${media.extension}`;
		let quote;
		try { quote = pointQuote(INDEPENDENT_QUOTE, loadBillingSettings()); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
		const account = await ensureUserAccount(db, user.id);
		const claimedWeek = await claimFreeWeek(db, user.id, new Date());
		let reservedPoints = 0;
		let reservationId: string | null = null;
		if (claimedWeek === null) {
			try {
				const reservation = await reserveInSession(db, account.id, quote.points, "independent_evaluation", `independent-evaluation:${id}`);
				reservationId = reservation.id;
				reservedPoints = quote.points;
			} catch (cause) {
				if (cause instanceof InsufficientPointsError) return error("INSUFFICIENT_POINTS", `This evaluation requires up to ${quote.points} points`, 402);
				throw cause;
			}
		}
		await db.transaction(async (tx) => {
			await tx.insert(independentEvaluations).values({ id, userId: user.id, storageKey, originalName: file.name, mediaType: media.mediaType, jobDescription: pastedDescription || null, jobDescriptionKey, jobDescriptionMediaType, status: "queued", pointReservationId: reservationId, freeWeekStart: claimedWeek, retentionDate: new Date(Date.now() + (config.independentRetentionDays || 30) * 86400000) });
			await tx.insert(processingJobs).values({ id: processingId, type: "independent_evaluation_processing", payloadReference: id, idempotencyKey: id });
		});
		await persistObject(config.storageRoot, storageKey, content);
		if (jobDescriptionKey && jobDescriptionContent) await persistObject(config.storageRoot, jobDescriptionKey, jobDescriptionContent);
		return c.json({ id, processingJobId: processingId, freeEvaluation: claimedWeek !== null, reservedPoints }, 202);
	});

	app.get("/api/independent-evaluations", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "candidate") return error("UNAUTHORIZED", "Candidate access required", 401);
		const rows = await db.select().from(independentEvaluations).where(eq(independentEvaluations.userId, user.id)).orderBy(desc(independentEvaluations.createdAt));
		return c.json(rows.map((item) => ({ id: item.id, status: item.status, score: item.score, originalName: item.originalName, createdAt: item.createdAt, completedAt: item.completedAt, safeError: item.safeError, hasImprovedResume: Boolean(item.improvedResumeKey) })));
	});

	app.get("/api/independent-evaluations/:evaluationId", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "candidate") return error("UNAUTHORIZED", "Candidate access required", 401);
		const item = (await db.select().from(independentEvaluations).where(and(eq(independentEvaluations.id, c.req.param("evaluationId")), eq(independentEvaluations.userId, user.id))).limit(1))[0]; if (!item) return error("NOT_FOUND", "Evaluation not found", 404);
		return c.json({ id: item.id, status: item.status, score: item.score, originalName: item.originalName, createdAt: item.createdAt, completedAt: item.completedAt, safeError: item.safeError, suggestions: item.suggestions ?? [], facts: item.normalizedFacts ?? {}, hasImprovedResume: Boolean(item.improvedResumeKey) });
	});

	app.delete("/api/independent-evaluations/:evaluationId", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "candidate") return error("UNAUTHORIZED", "Candidate access required", 401);
		const item = (await db.select().from(independentEvaluations).where(and(eq(independentEvaluations.id, c.req.param("evaluationId")), eq(independentEvaluations.userId, user.id))).limit(1))[0]; if (!item) return error("NOT_FOUND", "Evaluation not found", 404);
		if (item.pointReservationId) await releaseInSession(db, item.pointReservationId);
		const storage = new LocalObjectStorage(config.storageRoot);
		for (const key of [item.storageKey, item.jobDescriptionKey, item.improvedResumeKey]) if (key) await storage.delete(key);
		await db.delete(processingJobs).where(and(eq(processingJobs.type, "independent_evaluation_processing"), eq(processingJobs.payloadReference, item.id))); await db.delete(independentEvaluations).where(eq(independentEvaluations.id, item.id)); return new Response(null, { status: 204 });
	});

	app.get("/api/independent-evaluations/:evaluationId/improved-resume", async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "candidate") return error("UNAUTHORIZED", "Candidate access required", 401);
		const item = (await db.select().from(independentEvaluations).where(and(eq(independentEvaluations.id, c.req.param("evaluationId")), eq(independentEvaluations.userId, user.id))).limit(1))[0];
		if (!item || !item.improvedResumeKey) return error("NOT_FOUND", "Corrected resume is not available", 404);
		try {
			const content = await new LocalObjectStorage(config.storageRoot).get(item.improvedResumeKey);
			return new Response(content as unknown as BodyInit, { headers: { "Content-Type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "Content-Disposition": 'attachment; filename="corrected-resume.docx"' } });
		} catch {
			return error("NOT_FOUND", "Corrected resume is not available", 404);
		}
	});

	const redeem = async (c: import("hono").Context<{ Variables: Variables }>, value: string) => {
		const user = requireUser(c); if (!user || user.accountType !== "candidate") return error("UNAUTHORIZED", "Candidate access required", 401);
		const invitation = (await db.select().from(invitations).where(eq(invitations.tokenHash, digest(value))).limit(1))[0] ?? (await db.select().from(invitations).where(eq(invitations.passcodeHash, digest(value.trim().toUpperCase()))).limit(1))[0];
		if (!invitation || invitation.revokedAt || invitation.expiresAt <= new Date()) return error("NOT_FOUND", "Invitation is unavailable", 404);
		if (invitation.redeemingUserId && invitation.redeemingUserId !== user.id) return error("INVITATION_REDEEMED", "Invitation was redeemed by another user", 409);
		await db.update(invitations).set({ redeemingUserId: user.id }).where(eq(invitations.id, invitation.id));
		return c.json({ jobId: invitation.jobId, invitationId: invitation.id });
	};
	app.post("/api/invitations/:token/redeem", (c) => redeem(c, c.req.param("token")));
	app.post("/api/invitations/redeem", zValidator("json", z.object({ passcode: z.string().min(1) })), (c) => redeem(c, c.req.valid("json").passcode));

	app.get("/api/organizations/:organizationId/members", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.param("organizationId");
		const access = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!access[0]) return error("NOT_FOUND", "Organization not found", 404);
		const members = await db.select({ member: organizationMembers, user: { id: users.id, name: users.name, email: users.email } }).from(organizationMembers).innerJoin(users, eq(users.id, organizationMembers.userId)).where(eq(organizationMembers.organizationId, organizationId));
		return c.json(members.map(({ member, user: memberUser }) => ({ userId: member.userId, name: memberUser.name, email: memberUser.email, role: member.role })));
	});

	app.post("/api/organizations/:organizationId/members", zValidator("json", z.object({ email: z.string().email(), role: z.enum(["recruiter", "viewer"]) })), async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401);
		const organizationId = c.req.param("organizationId"); const input = c.req.valid("json");
		const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1); if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403);
		const memberUser = (await db.select().from(users).where(eq(users.email, input.email.toLowerCase())).limit(1))[0]; if (!memberUser || memberUser.accountType !== "employer") return error("NOT_FOUND", "Employer user not found", 404);
		try { await db.insert(organizationMembers).values({ id: crypto.randomUUID(), organizationId, userId: memberUser.id, role: input.role }); } catch (cause) { if (String(cause).includes("uq_organization_member")) return error("MEMBER_EXISTS", "User is already a member", 409); throw cause; }
		return c.json({ userId: memberUser.id, role: input.role }, 201);
	});

	app.delete("/api/organizations/:organizationId/members/:memberUserId", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.param("organizationId"); const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1); if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403);
		const member = (await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, c.req.param("memberUserId")))).limit(1))[0]; if (!member) return error("NOT_FOUND", "Organization member not found", 404); if (member.role === "owner") return error("OWNER_REQUIRED", "Organization owner cannot be removed", 409);
		await db.delete(organizationMembers).where(eq(organizationMembers.id, member.id)); return new Response(null, { status: 204 });
	});

	app.get("/api/organizations/:organizationId/join-policy", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401); const organizationId = c.req.param("organizationId"); const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1); if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403);
		const organization = (await db.select().from(organizations).where(eq(organizations.id, organizationId)).limit(1))[0]; if (!organization) return error("NOT_FOUND", "Organization not found", 404); const domains = await db.select({ domain: organizationEmailDomains.domain }).from(organizationEmailDomains).where(eq(organizationEmailDomains.organizationId, organizationId)); const emails = await db.select({ email: organizationAllowedEmails.email }).from(organizationAllowedEmails).where(eq(organizationAllowedEmails.organizationId, organizationId)); return c.json({ defaultRole: organization.defaultMemberRole, domains: domains.map((item) => item.domain).sort(), emails: emails.map((item) => item.email).sort() });
	});

	app.put("/api/organizations/:organizationId/join-policy", zValidator("json", z.object({ defaultRole: z.enum(["recruiter", "viewer"]) })), async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401); const organizationId = c.req.param("organizationId"); const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1); if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403); const role = c.req.valid("json").defaultRole; await db.update(organizations).set({ defaultMemberRole: role, updatedAt: new Date() }).where(eq(organizations.id, organizationId)); return c.json({ defaultRole: role });
	});

	app.post("/api/organizations/:organizationId/join-policy/domains", zValidator("json", z.object({ domain: z.string().min(3).max(253) })), async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401); const organizationId = c.req.param("organizationId"); const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1); if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403); const domain = c.req.valid("json").domain.trim().toLowerCase().replace(/^@/, ""); if (!domain.includes(".") || /\s/.test(domain)) return error("INVALID_REQUEST", "Enter a valid email domain", 400); try { await db.insert(organizationEmailDomains).values({ id: crypto.randomUUID(), organizationId, domain }); } catch (cause) { if (String(cause).includes("uq_organization_email_domain")) return error("RULE_EXISTS", "Domain is already claimed", 409); throw cause; } return c.json({ domain }, 201);
	});

	app.post("/api/organizations/:organizationId/join-policy/emails", zValidator("json", z.object({ email: z.string().email() })), async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401); const organizationId = c.req.param("organizationId"); const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1); if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403); const email = c.req.valid("json").email.toLowerCase(); try { await db.insert(organizationAllowedEmails).values({ id: crypto.randomUUID(), organizationId, email }); } catch (cause) { if (String(cause).includes("uq_organization_allowed_email")) return error("RULE_EXISTS", "Email is already in the join policy", 409); throw cause; } return c.json({ email }, 201);
	});

	app.delete("/api/organizations/:organizationId/join-policy/domains/:domain", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.param("organizationId");
		const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1);
		if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403);
		await db.delete(organizationEmailDomains).where(and(eq(organizationEmailDomains.organizationId, organizationId), eq(organizationEmailDomains.domain, c.req.param("domain").toLowerCase())));
		return new Response(null, { status: 204 });
	});

	app.delete("/api/organizations/:organizationId/join-policy/emails/:email", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.param("organizationId");
		const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1);
		if (!owner[0]) return error("FORBIDDEN", "Owner access required", 403);
		await db.delete(organizationAllowedEmails).where(and(eq(organizationAllowedEmails.organizationId, organizationId), eq(organizationAllowedEmails.email, c.req.param("email").toLowerCase())));
		return new Response(null, { status: 204 });
	});

	app.put("/api/jobs/:jobId/application-window", zValidator("json", z.object({ opensAt: z.coerce.date(), closesAt: z.coerce.date() })), async (c) => {
		const user = requireUser(c); if (!user || user.accountType !== "employer") return error("UNAUTHORIZED", "Employer access required", 401); const input = c.req.valid("json"); if (input.closesAt <= input.opensAt) return error("INVALID_REQUEST", "Application close must be after application open", 400);
		const job = (await db.select().from(jobs).where(eq(jobs.id, c.req.param("jobId"))).limit(1))[0]; if (!job) return error("NOT_FOUND", "Job not found", 404); const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, job.organizationId), eq(organizationMembers.userId, user.id))).limit(1); if (!member[0] || !["owner", "recruiter"].includes(member[0].role)) return error("FORBIDDEN", "Recruiter access required", 403);
		await db.update(jobs).set({ applicationOpensAt: input.opensAt, applicationClosesAt: input.closesAt, updatedAt: new Date() }).where(eq(jobs.id, job.id)); return c.json({ opensAt: input.opensAt, closesAt: input.closesAt });
	});

	app.get("/api/jobs/:jobId/evaluations", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const job = (await db.select().from(jobs).where(eq(jobs.id, c.req.param("jobId"))).limit(1))[0]; if (!job) return error("NOT_FOUND", "Job not found", 404);
		const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, job.organizationId), eq(organizationMembers.userId, user.id))).limit(1); if (!member[0]) return error("NOT_FOUND", "Job not found", 404);
		const eligibilityFilter = c.req.queries("eligibility") ?? [];
		const statusFilter = c.req.queries("status") ?? [];
		const outcomeFilter = c.req.queries("outcome") ?? [];
		if (statusFilter.length && !statusFilter.every((item) => VALID_EVALUATION_STATUSES.has(item))) return error("INVALID_REQUEST", "Unknown processing status filter", 400);
		if (outcomeFilter.length && !outcomeFilter.every((item) => VALID_ASSESSMENT_OUTCOMES.has(item))) return error("INVALID_REQUEST", "Unknown requirement outcome filter", 400);
		const minimumScore = c.req.query("minimum_score") ?? c.req.query("minimumScore");
		const minimumCoverage = c.req.query("minimum_coverage") ?? c.req.query("minimumCoverage");
		const search = (c.req.query("search") ?? "").trim().toLowerCase();
		const skill = (c.req.query("skill") ?? "").trim().toLowerCase();
		const limit = Math.min(Math.max(Number(c.req.query("limit") ?? 100), 1), 500);
		const rows = await db.select({ evaluation: evaluations, candidate: candidateRecords, version: resumeVersions }).from(evaluations).innerJoin(resumeSubmissions, eq(resumeSubmissions.id, evaluations.resumeSubmissionId)).innerJoin(candidateRecords, eq(candidateRecords.id, resumeSubmissions.candidateRecordId)).innerJoin(resumeVersions, eq(resumeVersions.id, evaluations.resumeVersionId)).where(eq(resumeSubmissions.jobId, job.id));
		let filtered = rows;
		if (eligibilityFilter.length) filtered = filtered.filter(({ evaluation }) => eligibilityFilter.includes(evaluation.eligibility));
		if (minimumScore !== undefined) filtered = filtered.filter(({ evaluation }) => (evaluation.score ?? -1) >= Number(minimumScore));
		if (minimumCoverage !== undefined) filtered = filtered.filter(({ evaluation }) => (evaluation.evidenceCoverage ?? -1) >= Number(minimumCoverage));
		if (statusFilter.length) filtered = filtered.filter(({ evaluation }) => statusFilter.includes(evaluation.status));
		if (search) filtered = filtered.filter(({ candidate }) => (candidate.fullName ?? "").toLowerCase().includes(search) || (candidate.email ?? "").toLowerCase().includes(search));
		if (skill) filtered = filtered.filter(({ version }) => skillNamesFromFacts(version.normalizedFacts).some((name) => name.toLowerCase().includes(skill)));
		filtered = filtered.sort((a, b) => (b.evaluation.score ?? -1) - (a.evaluation.score ?? -1));
		if (outcomeFilter.length) {
			const matching = new Set<string>();
			for (const { evaluation } of filtered) {
				const assessments = await db.execute(sql`SELECT outcome FROM requirement_assessment WHERE evaluation_id = ${evaluation.id}`);
				if ((assessments as unknown as Array<{ outcome: string }>).some((item) => outcomeFilter.includes(item.outcome))) matching.add(evaluation.id);
			}
			filtered = filtered.filter(({ evaluation }) => matching.has(evaluation.id));
		}
		const result = [];
		for (const { evaluation, candidate, version } of filtered.slice(0, limit)) {
			const assessments = await db.execute(sql`SELECT a.outcome, a.confidence, a.reasoning, a.evidence, a.semantic_evidence, a.lexical_evidence, r.normalized_text, r.kind, r.weight FROM requirement_assessment a JOIN job_requirement r ON r.id = a.job_requirement_id WHERE a.evaluation_id = ${evaluation.id}`);
			const triples = (assessments as unknown as Array<{ outcome: string; kind: string; weight: number; normalized_text: string; confidence: number; reasoning: string; evidence: unknown; semantic_evidence: unknown; lexical_evidence: unknown }>).map((item) => ({ ...item }));
			const contributions = contributionByIndex(triples);
			const quality = qualityFromVersion({ qualityState: version.qualityState, extractionBlocks: version.extractionBlocks, normalizedFacts: version.normalizedFacts });
			result.push({
				id: evaluation.id, candidateName: candidate.fullName, candidateEmail: candidate.email, candidateLocation: candidate.location,
				status: evaluation.status, score: evaluation.score, coverage: evaluation.evidenceCoverage, eligibility: evaluation.eligibility,
				skills: skillNamesFromFacts(version.normalizedFacts),
				hardGates: triples.filter((item) => item.kind === "hard_gate").map((item) => ({ requirement: item.normalized_text, outcome: item.outcome })),
				...quality,
				assessments: triples.map((item, index) => ({ requirement: item.normalized_text, outcome: item.outcome, kind: item.kind, weight: item.weight, contribution: contributions[index], reasoning: item.reasoning, evidence: item.evidence, semanticEvidence: item.semantic_evidence, lexicalEvidence: item.lexical_evidence })),
			});
		}
		return c.json(result);
	});

	app.get("/api/jobs/:jobId/evaluations.csv", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const job = (await db.select().from(jobs).where(eq(jobs.id, c.req.param("jobId"))).limit(1))[0]; if (!job) return error("NOT_FOUND", "Job not found", 404);
		const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, job.organizationId), eq(organizationMembers.userId, user.id))).limit(1); if (!member[0]) return error("NOT_FOUND", "Job not found", 404);
		const columns = c.req.queries("columns") ?? [];
		const labels = c.req.queries("labels") ?? [];
		const keys = columns.length ? [...new Set(columns)] : Object.keys(EXPORT_COLUMNS);
		const unknown = keys.filter((key) => !(key in EXPORT_COLUMNS));
		if (unknown.length) return error("INVALID_REQUEST", `Unknown export column: ${unknown[0]}`, 400);
		if (labels.length && labels.length !== keys.length) return error("INVALID_REQUEST", "Export labels must match the selected columns", 400);
		const headers = keys.map((key, index) => (labels[index]?.trim() || EXPORT_COLUMNS[key]) as string);
		const rows = await db.select({ evaluation: evaluations, candidate: candidateRecords, version: resumeVersions }).from(evaluations).innerJoin(resumeSubmissions, eq(resumeSubmissions.id, evaluations.resumeSubmissionId)).innerJoin(candidateRecords, eq(candidateRecords.id, resumeSubmissions.candidateRecordId)).innerJoin(resumeVersions, eq(resumeVersions.id, evaluations.resumeVersionId)).where(eq(resumeSubmissions.jobId, job.id));
		const lines = [headers.map(escapeCsvCell).join(",")];
		for (const { evaluation, candidate, version } of rows) {
			const quality = qualityFromVersion({ qualityState: version.qualityState, extractionBlocks: version.extractionBlocks, normalizedFacts: version.normalizedFacts });
			const values: Record<string, unknown> = {
				candidate_name: candidate.fullName ?? "", candidate_email: candidate.email ?? "", candidate_location: candidate.location ?? "",
				status: evaluation.status, score: evaluation.score ?? "", eligibility: evaluation.eligibility,
				evidence_coverage: evaluation.evidenceCoverage ?? "", quality_state: quality.qualityState, quality_warnings: quality.qualityWarnings.join("; "),
			};
			lines.push(keys.map((key) => escapeCsvCell(values[key])).join(","));
		}
		return new Response(lines.join("\n"), { headers: { "Content-Type": "text/csv; charset=utf-8", "Content-Disposition": `attachment; filename="${job.id}-evaluations.csv"` } });
	});

	app.get("/api/me/points", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.query("organization_id") ?? c.req.query("organizationId") ?? undefined;
		if (!organizationId) {
			const account = await ensureUserAccount(db, user.id);
			const freeUsed = (await db.select({ id: weeklyFreeUses.id }).from(weeklyFreeUses).where(and(eq(weeklyFreeUses.userId, user.id), eq(weeklyFreeUses.weekStart, weekStart(new Date())))).limit(1))[0];
			return c.json({ scope: "personal", accountId: account.id, balance: await balance(db, account.id), available: await availableBalance(db, account.id), allowance: { freeUsedThisWeek: Boolean(freeUsed), resetsAt: nextReset(new Date()).toISOString() } });
		}
		const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id))).limit(1);
		if (!member[0]) return error("NOT_FOUND", "Organization not found", 404);
		const account = await ensureOrganizationAccount(db, organizationId);
		const entitlement = (await db.execute(sql`SELECT id FROM organization_entitlement WHERE organization_id = ${organizationId} LIMIT 1`))[0];
		return c.json({ scope: "organization", organizationId, accountId: account.id, balance: await balance(db, account.id), available: await availableBalance(db, account.id), enterprise: Boolean(entitlement) });
	});

	app.get("/api/billing/packs", (c) => {
		try { return c.json(loadBillingSettings().packs.map((pack) => ({ id: pack.id, points: pack.points, amountInr: pack.amountInr }))); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
	});

	app.get("/api/billing/quote", (c) => {
		const kind = c.req.query("kind") ?? INDEPENDENT_QUOTE;
		try {
			const quote = pointQuote(kind, loadBillingSettings());
			return c.json({ kind: quote.kind, points: quote.points, minimumPoints: quote.minimumPoints, costCeilingPoints: quote.costCeilingPoints, lineItems: quote.lineItems.map((item) => ({ task: item.task, maxInputTokens: item.maxInputTokens, maxOutputTokens: item.maxOutputTokens })) });
		} catch (cause) {
			if (cause instanceof UnknownQuoteKindError) return error("INVALID_REQUEST", "Unknown quote kind", 400);
			throw cause;
		}
	});

	app.get("/api/billing/ledger", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const organizationId = c.req.query("organization_id") ?? c.req.query("organizationId") ?? undefined;
		let accountId: string;
		if (!organizationId) {
			accountId = (await ensureUserAccount(db, user.id)).id;
		} else {
			const owner = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, organizationId), eq(organizationMembers.userId, user.id), eq(organizationMembers.role, "owner"))).limit(1);
			if (!owner[0]) return error("NOT_FOUND", "Organization not found", 404);
			accountId = (await ensureOrganizationAccount(db, organizationId)).id;
		}
		const rows = await db.execute(sql`SELECT amount, reason, created_at FROM point_ledger_entry WHERE account_id = ${accountId} ORDER BY created_at DESC LIMIT 100`);
		return c.json((rows as unknown as Array<{ amount: number; reason: string; created_at: string }>).map((entry) => ({ amount: entry.amount, reason: entry.reason, createdAt: entry.created_at })));
	});

	app.post("/api/billing/orders", zValidator("json", z.object({ packId: z.string().min(1), organizationId: z.string().optional() })), async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		let billing;
		try { billing = loadBillingSettings(); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
		const input = c.req.valid("json");
		const pack = billing.packs.find((item) => item.id === input.packId);
		if (!pack) return error("INVALID_PACK", "Unknown point pack", 400);
		let client: RazorpayClient;
		try { client = new RazorpayClient(billing.razorpayKeyId, billing.razorpayKeySecret); } catch (cause) { return error("SERVICE_UNAVAILABLE", cause instanceof Error ? cause.message : "Razorpay is unavailable", 503); }
		const orderId = crypto.randomUUID();
		let remote: Record<string, unknown>;
		try { remote = await client.createOrder(pack.amountInr * 100, "INR", orderId, { packId: pack.id, points: String(pack.points) }); } catch (cause) { return error("SERVICE_UNAVAILABLE", cause instanceof RazorpayUnavailableError ? cause.message : cause instanceof RazorpayError ? cause.message : "Razorpay is unavailable", 503); }
		const remoteId = typeof remote["id"] === "string" ? remote["id"] : null;
		if (!remoteId) return error("SERVICE_UNAVAILABLE", "Razorpay order response is invalid", 503);
		if (input.organizationId) {
			const role = (await db.execute(sql`SELECT role FROM organization_member WHERE organization_id = ${input.organizationId} AND user_id = ${user.id} LIMIT 1`))[0] as { role: string } | undefined;
			if (role?.role !== "owner") return error("NOT_FOUND", "Organization not found", 404);
			const account = await ensureOrganizationAccount(db, input.organizationId);
			await db.execute(sql`INSERT INTO razorpay_order (id, razorpay_order_id, account_id, purchaser_user_id, pack_id, points, amount_inr, currency, status, created_at, updated_at) VALUES (${orderId}, ${remoteId}, ${account.id}, ${user.id}, ${pack.id}, ${pack.points}, ${pack.amountInr}, 'INR', 'created', now(), now())`);
		} else {
			const account = await ensureUserAccount(db, user.id);
			await db.execute(sql`INSERT INTO razorpay_order (id, razorpay_order_id, account_id, purchaser_user_id, pack_id, points, amount_inr, currency, status, created_at, updated_at) VALUES (${orderId}, ${remoteId}, ${account.id}, ${user.id}, ${pack.id}, ${pack.points}, ${pack.amountInr}, 'INR', 'created', now(), now())`);
		}
		return c.json({ id: orderId, razorpayOrderId: remoteId, razorpayKeyId: billing.razorpayKeyId, amountInr: pack.amountInr, currency: "INR", packId: pack.id, points: pack.points }, 201);
	});

	app.post("/api/billing/orders/:orderId/verify", zValidator("json", z.object({ razorpayPaymentId: z.string().min(1), razorpaySignature: z.string().min(1) })), async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const order = (await db.execute(sql`SELECT ro.id, ro.razorpay_order_id FROM razorpay_order ro WHERE ro.id = ${c.req.param("orderId")} AND ro.purchaser_user_id = ${user.id}`))[0] as { id: string; razorpay_order_id: string } | undefined;
		if (!order) return error("NOT_FOUND", "Order not found", 404);
		const existing = (await db.execute(sql`SELECT signature_verified FROM razorpay_payment WHERE razorpay_payment_id = ${c.req.valid("json").razorpayPaymentId} AND order_row_id = ${order.id}`))[0] as { signature_verified: boolean } | undefined;
		if (existing?.signature_verified) return c.json({ verified: true });
		const input = c.req.valid("json");
		let billing;
		try { billing = loadBillingSettings(); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
		if (!verifyCheckoutSignature(order.razorpay_order_id, input.razorpayPaymentId, input.razorpaySignature, billing.razorpayKeySecret)) {
			return error("INVALID_SIGNATURE", "Checkout signature verification failed", 400);
		}
		await db.execute(sql`INSERT INTO razorpay_payment (id, razorpay_payment_id, order_row_id, status, amount_inr, points_granted, signature_verified, source, created_at, updated_at) SELECT ${crypto.randomUUID()}, ${input.razorpayPaymentId}, id, 'captured', amount_inr, false, true, 'checkout', now(), now() FROM razorpay_order WHERE id = ${order.id} ON CONFLICT (razorpay_payment_id) DO UPDATE SET signature_verified = true`);
		return c.json({ verified: true });
	});

	app.post("/api/billing/orders/:orderId/reconcile", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		let billing;
		try { billing = loadBillingSettings(); } catch { return error("SERVICE_UNAVAILABLE", "Billing configuration is invalid", 503); }
		let client: RazorpayClient;
		try { client = new RazorpayClient(billing.razorpayKeyId, billing.razorpayKeySecret); } catch (cause) { return error("SERVICE_UNAVAILABLE", cause instanceof Error ? cause.message : "Razorpay is unavailable", 503); }
		const order = (await db.execute(sql`SELECT id, razorpay_order_id, account_id, pack_id, points, amount_inr FROM razorpay_order WHERE id = ${c.req.param("orderId")} AND purchaser_user_id = ${user.id}`))[0] as { id: string; razorpay_order_id: string; account_id: string; pack_id: string; points: number; amount_inr: number } | undefined;
		if (!order) return error("NOT_FOUND", "Order not found", 404);
		let payments: Record<string, unknown>[];
		try { payments = await client.orderPayments(order.razorpay_order_id); } catch (cause) { return error("SERVICE_UNAVAILABLE", cause instanceof Error ? cause.message : "Razorpay is unavailable", 503); }
		const results = [];
		for (const payment of payments) {
			const paymentId = typeof payment["id"] === "string" ? payment["id"] : "";
			const status = String(payment["status"] ?? "");
			if (!paymentId) continue;
			await db.execute(sql`INSERT INTO razorpay_payment (id, razorpay_payment_id, order_row_id, status, method, amount_inr, points_granted, signature_verified, source, created_at, updated_at) VALUES (${crypto.randomUUID()}, ${paymentId}, ${order.id}, ${status}, ${typeof payment["method"] === "string" ? payment["method"] : null}, ${order.amount_inr}, false, false, 'reconciliation', now(), now()) ON CONFLICT (razorpay_payment_id) DO UPDATE SET status = EXCLUDED.status, updated_at = now()`);
			const granted = await grantForCaptured(db, order, paymentId, status);
			const refunded = await syncRefunds(db, order, payment);
			results.push({ razorpayPaymentId: paymentId, status, pointsGranted: granted, refundedInr: refunded });
		}
		return c.json({ orderId: order.id, payments: results });
	});

	app.post("/api/webhooks/razorpay", async (c) => {
		const body = new Uint8Array(await c.req.arrayBuffer());
		let billing;
		try { billing = loadBillingSettings(); } catch { return error("SERVICE_UNAVAILABLE", "Webhooks are not configured", 503); }
		if (!billing.razorpayWebhookSecret) return error("SERVICE_UNAVAILABLE", "Webhooks are not configured", 503);
		if (!verifyWebhookSignature(body, c.req.header("x-razorpay-signature") ?? "", billing.razorpayWebhookSecret)) return error("INVALID_SIGNATURE", "Webhook signature verification failed", 400);
		let payload: Record<string, unknown>;
		try { payload = JSON.parse(new TextDecoder().decode(body)) as Record<string, unknown>; } catch { return error("INVALID_REQUEST", "Webhook body must be JSON", 400); }
		if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return error("INVALID_REQUEST", "Webhook body must be JSON", 400);
		const eventId = c.req.header("x-razorpay-event-id") ?? digest(new TextDecoder().decode(body));
		const event = String(payload["event"] ?? "");
		const inserted = await db.execute(sql`INSERT INTO razorpay_webhook_event (id, event_type, payload, received_at) VALUES (${eventId}, ${event}, ${JSON.stringify(payload)}::jsonb, now()) ON CONFLICT (id) DO NOTHING RETURNING id`);
		if (!inserted.length) return c.json({ received: true });
		const payment = paymentEntity(payload);
		const paymentId = typeof payment["id"] === "string" ? payment["id"] : "";
		if (paymentId && (event.startsWith("payment.") || event.startsWith("order."))) {
			const order = (await db.execute(sql`SELECT id, account_id, pack_id, points, amount_inr FROM razorpay_order WHERE razorpay_order_id = ${String(payment["order_id"] ?? "")}`))[0] as { id: string; account_id: string; pack_id: string; points: number; amount_inr: number } | undefined;
			if (order) {
				await db.execute(sql`INSERT INTO razorpay_payment (id, razorpay_payment_id, order_row_id, status, method, amount_inr, points_granted, signature_verified, source, created_at, updated_at) VALUES (${crypto.randomUUID()}, ${paymentId}, ${order.id}, ${String(payment["status"] ?? "")}, ${typeof payment["method"] === "string" ? payment["method"] : null}, ${order.amount_inr}, false, true, 'webhook', now(), now()) ON CONFLICT (razorpay_payment_id) DO UPDATE SET status = EXCLUDED.status, updated_at = now()`);
				await grantForCaptured(db, order, paymentId, String(payment["status"] ?? ""));
				await syncRefunds(db, order, payment);
			}
		}
		await db.execute(sql`UPDATE razorpay_webhook_event SET processed_at = now() WHERE id = ${eventId}`);
		return c.json({ received: true });
	});

	app.post("/api/admin/organizations/:organizationId/entitlement", zValidator("json", z.object({ note: z.string().max(500).default("") })), async (c) => {
		if (!isAdmin(c)) return error("NOT_FOUND", "Not found", 404);
		const organizationId = c.req.param("organizationId");
		const existing = (await db.execute(sql`SELECT id FROM organization_entitlement WHERE organization_id = ${organizationId}`))[0];
		if (existing) return error("INVALID_REQUEST", "Entitlement already exists", 409);
		await db.execute(sql`INSERT INTO organization_entitlement (id, organization_id, provisioned_by, note, created_at) VALUES (${crypto.randomUUID()}, ${organizationId}, 'admin', ${c.req.valid("json").note.trim() || null}, now())`);
		return c.json({ organizationId, note: c.req.valid("json").note }, 201);
	});

	app.delete("/api/admin/organizations/:organizationId/entitlement", async (c) => {
		if (!isAdmin(c)) return error("NOT_FOUND", "Not found", 404);
		await db.execute(sql`DELETE FROM organization_entitlement WHERE organization_id = ${c.req.param("organizationId")}`);
		return new Response(null, { status: 204 });
	});

	app.post("/api/admin/retention/sweep", async (c) => {
		if (!isAdmin(c)) return error("NOT_FOUND", "Not found", 404);
		const result = await purgeExpiredData(db, new LocalObjectStorage(config.storageRoot), new Date());
		return c.json({ documentsPurged: result.documentsPurged, independentEvaluationsPurged: result.independentEvaluationsPurged });
	});

	app.post("/api/demo/session", zValidator("json", z.object({ act: z.enum(["employer", "candidate"]) })), async (c) => {
		const act = c.req.valid("json").act;
		const demoEmail = act === "employer" ? "demo-employer@skillsignal.app" : "demo-candidate@skillsignal.app";
		let demoUser = (await db.select().from(users).where(eq(users.email, demoEmail)).limit(1))[0];
		if (!demoUser) {
			const id = crypto.randomUUID();
			await db.execute(sql`INSERT INTO "user" (id, name, email, account_type, email_verified, is_demo, created_at, updated_at) VALUES (${id}, ${act === "employer" ? "Demo Recruiter" : "Demo Candidate"}, ${demoEmail}, ${act}, true, true, now(), now()) ON CONFLICT DO NOTHING`);
			await db.execute(sql`INSERT INTO account (id, account_id, provider_id, user_id, password, created_at, updated_at) VALUES (${crypto.randomUUID()}, ${demoEmail}, 'credential', ${id}, ${createHash("sha256").update("demo-password").digest("hex")}, now(), now()) ON CONFLICT DO NOTHING`);
			demoUser = (await db.select().from(users).where(eq(users.email, demoEmail)).limit(1))[0];
		}
		if (!demoUser) return error("SERVICE_UNAVAILABLE", "Demo workspace is unavailable", 503);
		if (act === "employer") {
			const membership = await db.select().from(organizationMembers).where(eq(organizationMembers.userId, demoUser.id)).limit(1);
			if (!membership[0]) {
				const orgId = crypto.randomUUID();
				await db.execute(sql`INSERT INTO organization (id, name, created_at, updated_at) VALUES (${orgId}, 'Demo Organization', now(), now())`);
				await db.execute(sql`INSERT INTO organization_member (id, organization_id, user_id, role, created_at) VALUES (${crypto.randomUUID()}, ${orgId}, ${demoUser.id}, 'owner', now())`);
			}
		}
		const issued = await issueToken(demoUser as AuthUser, config.jwtSecret, config.jwtTtlSeconds);
		return c.json({ user: { id: demoUser.id, name: demoUser.name, email: demoUser.email, accountType: demoUser.accountType }, token: issued.token, tokenType: "Bearer", expiresAt: issued.expiresAt });
	});

	app.get("/api/processing-jobs/:processingJobId", async (c) => {
		const user = requireUser(c); if (!user) return error("UNAUTHORIZED", "Unauthorized", 401);
		const result = await db.select().from(processingJobs).where(eq(processingJobs.id, c.req.param("processingJobId"))).limit(1);
		const processing = result[0]; if (!processing) return error("NOT_FOUND", "Processing job not found", 404);
		const independent = (await db.execute(sql`SELECT user_id FROM independent_evaluation WHERE id = ${processing.payloadReference}`))[0] as { user_id: string } | undefined;
		if (independent) {
			if (independent.user_id !== user.id) return error("NOT_FOUND", "Processing job not found", 404);
		} else {
			const submission = (await db.execute(sql`SELECT organization_id FROM resume_submission WHERE resume_version_id = ${processing.payloadReference}`))[0] as { organization_id: string } | undefined;
			if (!submission) return error("NOT_FOUND", "Processing job not found", 404);
			const member = await db.select().from(organizationMembers).where(and(eq(organizationMembers.organizationId, submission.organization_id), eq(organizationMembers.userId, user.id))).limit(1);
			if (!member[0]) return error("NOT_FOUND", "Processing job not found", 404);
		}
		return c.json({ id: processing.id, status: processing.status, safeError: processing.safeError, retryable: processing.status === "ready" && processing.attemptCount < processing.maximumAttempts });
	});
	return app;
};

export const bootstrap = () => { const config = loadConfig(); const { db, client } = createDatabase(config.databaseUrl); const app = createApp(db, config); return { app, client, config }; };
