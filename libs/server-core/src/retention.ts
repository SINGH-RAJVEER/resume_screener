import { sql } from "drizzle-orm";
import type { Database } from "./db.ts";
import { LocalObjectStorage } from "./storage.ts";
import { releaseInSession } from "./points.ts";

export type RetentionResult = {
	readonly documentsPurged: number;
	readonly independentEvaluationsPurged: number;
};

export const independentStorageKeys = (evaluation: { storageKey: string; jobDescriptionKey: string | null; improvedResumeKey: string | null }): string[] =>
	[evaluation.storageKey, evaluation.jobDescriptionKey, evaluation.improvedResumeKey].filter((key): key is string => Boolean(key));

export const purgeExpiredData = async (db: Database, storage: LocalObjectStorage, now: Date): Promise<RetentionResult> => {
	const documents = await db.execute(sql`SELECT id, storage_key FROM resume_document WHERE retention_date <= ${now} ORDER BY retention_date`);
	const evaluations = await db.execute(sql`SELECT id, storage_key, job_description_key, improved_resume_key, point_reservation_id FROM independent_evaluation WHERE retention_date <= ${now} ORDER BY retention_date`);
	const documentRows = documents as unknown as Array<{ id: string; storage_key: string }>;
	const evaluationRows = evaluations as unknown as Array<{ id: string; storage_key: string; job_description_key: string | null; improved_resume_key: string | null; point_reservation_id: string | null }>;

	for (const evaluation of evaluationRows) {
		if (evaluation.point_reservation_id) await releaseInSession(db, evaluation.point_reservation_id);
		await db.execute(sql`DELETE FROM processing_job WHERE type = 'independent_evaluation_processing' AND payload_reference = ${evaluation.id}`);
		await db.execute(sql`DELETE FROM independent_evaluation WHERE id = ${evaluation.id}`);
	}

	if (documentRows.length) {
		const ids = documentRows.map((item) => item.id);
		const versions = (await db.execute(sql`SELECT id FROM resume_version WHERE resume_document_id IN (${sql.join(ids.map((id) => sql`${id}`), sql`, `)})`)) as unknown as Array<{ id: string }>;
		const versionIds = versions.map((item) => item.id);
		if (versionIds.length) {
			const holds = (await db.execute(sql`SELECT point_reservation_id FROM evaluation WHERE resume_version_id IN (${sql.join(versionIds.map((id) => sql`${id}`), sql`, `)})`)) as unknown as Array<{ point_reservation_id: string | null }>;
			for (const hold of holds) if (hold.point_reservation_id) await releaseInSession(db, hold.point_reservation_id);
			await db.execute(sql`DELETE FROM evaluation WHERE resume_version_id IN (${sql.join(versionIds.map((id) => sql`${id}`), sql`, `)})`);
			const submissions = (await db.execute(sql`SELECT id FROM resume_submission WHERE resume_version_id IN (${sql.join(versionIds.map((id) => sql`${id}`), sql`, `)})`)) as unknown as Array<{ id: string }>;
			const submissionIds = submissions.map((item) => item.id);
			if (submissionIds.length) {
				await db.execute(sql`DELETE FROM batch_evaluation_submission WHERE resume_submission_id IN (${sql.join(submissionIds.map((id) => sql`${id}`), sql`, `)})`);
				await db.execute(sql`DELETE FROM resume_submission WHERE id IN (${sql.join(submissionIds.map((id) => sql`${id}`), sql`, `)})`);
			}
			await db.execute(sql`DELETE FROM batch_evaluation WHERE id NOT IN (SELECT batch_evaluation_id FROM batch_evaluation_submission) AND id NOT IN (SELECT batch_evaluation_id FROM evaluation WHERE batch_evaluation_id IS NOT NULL)`);
		}
		await db.execute(sql`DELETE FROM resume_document WHERE id IN (${sql.join(ids.map((id) => sql`${id}`), sql`, `)})`);
	}

	for (const key of [...documentRows.map((item) => item.storage_key), ...evaluationRows.flatMap((item) => independentStorageKeys({ storageKey: item.storage_key, jobDescriptionKey: item.job_description_key, improvedResumeKey: item.improved_resume_key }))]) {
		await storage.delete(key);
	}

	return { documentsPurged: documentRows.length, independentEvaluationsPurged: evaluationRows.length };
};
