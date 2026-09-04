import { randomBytes } from "node:crypto";
import { eq, and } from "drizzle-orm";
import type { Database } from "@skillsignal/server-core/db";
import { weeklyFreeUses } from "@skillsignal/server-core/schema";

export const weekStart = (now: Date): Date => {
	const moment = new Date(now);
	const daysSinceMonday = (moment.getUTCDay() + 6) % 7;
	return new Date(Date.UTC(moment.getUTCFullYear(), moment.getUTCMonth(), moment.getUTCDate() - daysSinceMonday));
};

export const nextReset = (now: Date): Date => new Date(weekStart(now).getTime() + 7 * 24 * 60 * 60 * 1000);

export const claimFreeWeek = async (db: Database, userId: string, now: Date): Promise<Date | null> => {
	const start = weekStart(now);
	const existing = await db.select({ id: weeklyFreeUses.id }).from(weeklyFreeUses).where(and(eq(weeklyFreeUses.userId, userId), eq(weeklyFreeUses.weekStart, start))).limit(1);
	if (existing[0]) return null;
	await db.insert(weeklyFreeUses).values({ id: randomBytes(18).toString("base64url"), userId, weekStart: start });
	return start;
};
