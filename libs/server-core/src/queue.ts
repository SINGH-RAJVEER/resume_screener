import { and, eq, sql } from "drizzle-orm";
import type { Database } from "./db.ts";
import { processingJobs, type ProcessingJob } from "./schema.ts";

export type ClaimedJob = Pick<ProcessingJob, "id" | "type" | "payloadReference" | "attemptCount" | "maximumAttempts"> & { leaseToken: string };

export const claimJob = async (db: Database, leaseSeconds: number): Promise<ClaimedJob | null> => {
	const token = crypto.randomUUID();
	const rows = await db.execute(sql`
		WITH next_job AS (
			SELECT id FROM processing_job
			WHERE (status = 'ready' AND available_at <= now())
				OR (status = 'processing' AND lease_expires_at < now())
			ORDER BY available_at, created_at
			FOR UPDATE SKIP LOCKED LIMIT 1
		)
		UPDATE processing_job
		SET status = 'processing', lease_token = ${token},
			lease_expires_at = now() + (${leaseSeconds} || ' seconds')::interval,
			attempt_count = attempt_count + 1, updated_at = now()
		WHERE id IN (SELECT id FROM next_job)
		RETURNING id, type, payload_reference, attempt_count, maximum_attempts
	`);
	const row = rows[0] as { id: string; type: string; payload_reference: string; attempt_count: number; maximum_attempts: number } | undefined;
	return row ? { id: row.id, type: row.type, payloadReference: row.payload_reference, attemptCount: row.attempt_count, maximumAttempts: row.maximum_attempts, leaseToken: token } : null;
};

export const updateLease = async (db: Database, job: ClaimedJob, leaseSeconds: number): Promise<boolean> => {
	const result = await db.update(processingJobs).set({ leaseExpiresAt: new Date(Date.now() + leaseSeconds * 1000), updatedAt: new Date() }).where(and(eq(processingJobs.id, job.id), eq(processingJobs.leaseToken, job.leaseToken), eq(processingJobs.status, "processing"))).returning({ id: processingJobs.id });
	return result.length === 1;
};

export const finishJob = async (db: Database, job: ClaimedJob, status: "completed" | "ready" | "dead", safeError: string | null, availableAt?: Date): Promise<boolean> => {
	const result = await db.update(processingJobs).set({ status, safeError, availableAt, leaseToken: null, leaseExpiresAt: null, updatedAt: new Date() }).where(and(eq(processingJobs.id, job.id), eq(processingJobs.leaseToken, job.leaseToken))).returning({ id: processingJobs.id });
	return result.length === 1;
};
