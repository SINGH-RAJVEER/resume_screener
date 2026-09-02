import { compare, hash } from "bcryptjs";
import { SignJWT, jwtVerify } from "jose";
import type { Context } from "hono";
import { and, eq } from "drizzle-orm";
import type { Database } from "@skillsignal/server-core/db";
import { accounts, users } from "@skillsignal/server-core/schema";

export const JWT_ISSUER = "skillsignal-api";
const accountId = (email: string) => `credential:${email}`;

export type AuthUser = typeof users.$inferSelect;

export const issueToken = async (user: AuthUser, secret: string, ttlSeconds: number): Promise<{ token: string; expiresAt: Date }> => {
	const expiresAt = new Date(Date.now() + ttlSeconds * 1000);
	const token = await new SignJWT({})
		.setProtectedHeader({ alg: "HS256" })
		.setIssuer(JWT_ISSUER)
		.setSubject(user.id)
		.setIssuedAt()
		.setExpirationTime(Math.floor(expiresAt.getTime() / 1000))
		.sign(new TextEncoder().encode(secret));
	return { token, expiresAt };
};

export const authenticate = async (db: Database, token: string, secret: string): Promise<AuthUser | null> => {
	try {
		const { payload } = await jwtVerify(token, new TextEncoder().encode(secret), { issuer: JWT_ISSUER, algorithms: ["HS256"] });
		if (typeof payload.sub !== "string") return null;
		const result = await db.select().from(users).where(eq(users.id, payload.sub)).limit(1);
		return result[0] ?? null;
	} catch {
		return null;
	}
};

export const register = async (db: Database, name: string, email: string, password: string, accountType: "candidate" | "employer"): Promise<AuthUser> => {
	const id = crypto.randomUUID();
	const passwordHash = await hash(password, 10);
	return await db.transaction(async (tx) => {
		const created = await tx.insert(users).values({ id, name: name.trim(), email: email.trim().toLowerCase(), accountType }).returning();
		if (!created[0]) throw new Error("User creation failed");
		await tx.insert(accounts).values({ id: crypto.randomUUID(), accountId: accountId(created[0].email), providerId: "credential", userId: id, password: passwordHash });
		return created[0];
	});
};

export const signIn = async (db: Database, email: string, password: string, accountType: "candidate" | "employer"): Promise<AuthUser | null> => {
	const result = await db.select({ user: users, password: accounts.password }).from(users).innerJoin(accounts, and(eq(accounts.userId, users.id), eq(accounts.providerId, "credential"))).where(and(eq(users.email, email.trim().toLowerCase()), eq(users.accountType, accountType))).limit(1);
	const row = result[0];
	return row?.password && await compare(password, row.password) ? row.user : null;
};

export const bearerUser = async (c: Context<{ Variables: { user: AuthUser } }>): Promise<AuthUser | null> => c.get("user") ?? null;
