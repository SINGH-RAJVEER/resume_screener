import postgres from "postgres";
import { drizzle, type PostgresJsDatabase } from "drizzle-orm/postgres-js";
import * as schema from "./schema.ts";

export type Database = PostgresJsDatabase<typeof schema>;

export const createDatabase = (url: string): { db: Database; client: postgres.Sql } => {
	const client = postgres(url, { max: Number(Bun.env["DATABASE_POOL_SIZE"] ?? 10) });
	return { client, db: drizzle(client, { schema }) };
};

export { schema };
