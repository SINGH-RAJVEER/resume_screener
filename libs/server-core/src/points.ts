import { randomBytes } from "node:crypto";
import { eq, sql } from "drizzle-orm";
import type { Database } from "./db.ts";
import { pointAccounts, pointLedgerEntries, pointReservations } from "./schema.ts";

export class InsufficientPointsError extends Error {}
export class ReservationStateError extends Error {}

const newId = (): string => randomBytes(18).toString("base64url");

export const ensureUserAccount = async (db: Database, userId: string): Promise<{ id: string }> => {
	const existing = (await db.select({ id: pointAccounts.id }).from(pointAccounts).where(eq(pointAccounts.ownerUserId, userId)).limit(1))[0];
	if (existing) return existing;
	const created = (await db.insert(pointAccounts).values({ id: newId(), ownerUserId: userId }).returning({ id: pointAccounts.id }))[0];
	if (!created) throw new Error("Point account creation failed");
	return created;
};

export const ensureOrganizationAccount = async (db: Database, organizationId: string): Promise<{ id: string }> => {
	const existing = (await db.select({ id: pointAccounts.id }).from(pointAccounts).where(eq(pointAccounts.organizationId, organizationId)).limit(1))[0];
	if (existing) return existing;
	const created = (await db.insert(pointAccounts).values({ id: newId(), organizationId }).returning({ id: pointAccounts.id }))[0];
	if (!created) throw new Error("Point account creation failed");
	return created;
};

export const balance = async (db: Database, accountId: string): Promise<number> => {
	const rows = await db.execute(sql`SELECT COALESCE(SUM(amount), 0)::int AS total FROM point_ledger_entry WHERE account_id = ${accountId}`);
	return Number((rows[0] as { total: number } | undefined)?.total ?? 0);
};

export const reservedTotal = async (db: Database, accountId: string): Promise<number> => {
	const rows = await db.execute(sql`SELECT COALESCE(SUM(amount), 0)::int AS total FROM point_reservation WHERE account_id = ${accountId} AND state = 'reserved'`);
	return Number((rows[0] as { total: number } | undefined)?.total ?? 0);
};

export const availableBalance = async (db: Database, accountId: string): Promise<number> =>
	(await balance(db, accountId)) - (await reservedTotal(db, accountId));

export const grantInSession = async (db: Database, accountId: string, amount: number, reason: string, idempotencyKey: string): Promise<number> => {
	if (amount <= 0) throw new Error("Grant amounts must be positive");
	const existing = await db.select({ id: pointLedgerEntries.id }).from(pointLedgerEntries).where(eq(pointLedgerEntries.idempotencyKey, idempotencyKey)).limit(1);
	if (existing[0]) return balance(db, accountId);
	await db.insert(pointLedgerEntries).values({ id: newId(), accountId, amount, reason, idempotencyKey });
	return balance(db, accountId);
};

export const reserveInSession = async (db: Database, accountId: string, amount: number, purpose: string, idempotencyKey: string): Promise<{ id: string; amount: number }> => {
	if (amount <= 0) throw new Error("Reservation amounts must be positive");
	const existing = (await db.select().from(pointReservations).where(eq(pointReservations.idempotencyKey, idempotencyKey)).limit(1))[0];
	if (existing) return { id: existing.id, amount: existing.amount };
	if ((await availableBalance(db, accountId)) < amount) throw new InsufficientPointsError("Insufficient points");
	const created = (await db.insert(pointReservations).values({ id: newId(), accountId, amount, purpose, idempotencyKey }).returning({ id: pointReservations.id, amount: pointReservations.amount }))[0];
	if (!created) throw new Error("Point reservation failed");
	return created;
};

export const settleInSession = async (db: Database, reservationId: string, chargedAmount: number, reason: string): Promise<void> => {
	const reservation = (await db.select().from(pointReservations).where(eq(pointReservations.id, reservationId)).limit(1))[0];
	if (!reservation || reservation.state !== "reserved") return;
	const charge = Math.min(chargedAmount, reservation.amount);
	await db.insert(pointLedgerEntries).values({ id: newId(), accountId: reservation.accountId, amount: -charge, reason, idempotencyKey: `settle:${reservation.id}` }).onConflictDoNothing();
	await db.update(pointReservations).set({ state: "settled", updatedAt: new Date() }).where(eq(pointReservations.id, reservationId));
};

export const releaseInSession = async (db: Database, reservationId: string): Promise<void> => {
	const reservation = (await db.select().from(pointReservations).where(eq(pointReservations.id, reservationId)).limit(1))[0];
	if (!reservation || reservation.state !== "reserved") return;
	await db.update(pointReservations).set({ state: "released", updatedAt: new Date() }).where(eq(pointReservations.id, reservationId));
};
