import { existsSync } from "node:fs";
import { join, resolve } from "node:path";
import postgres from "postgres";
import { drizzle } from "drizzle-orm/postgres-js";
import { migrate } from "drizzle-orm/postgres-js/migrator";

const candidates = [
	resolve(join(import.meta.dir, "..", "..", "..", "libs", "server-core", "drizzle")),
	resolve(join(import.meta.dir, "..", "drizzle")),
	resolve(join(process.cwd(), "drizzle")),
	resolve(join(process.cwd(), "libs", "server-core", "drizzle")),
];

const migrationsFolder = candidates.find((path) => existsSync(path));
if (!migrationsFolder) {
	throw new Error(`Drizzle migrations directory not found (tried ${candidates.join(", ")})`);
}

const client = postgres(Bun.env["DATABASE_URL"] ?? "postgres://postgres:password@localhost:5432/skillsignal", { max: 1 });
try {
	await migrate(drizzle(client), { migrationsFolder });
	console.log(`Applied database migrations from ${migrationsFolder}`);
} finally {
	await client.end();
}
