import { defineConfig } from "drizzle-kit";

export default defineConfig({
	dialect: "postgresql",
	schema: "./src/schema.ts",
	out: "./drizzle",
	dbCredentials: { url: Bun.env["DATABASE_URL"] ?? "postgres://postgres:password@localhost:5432/skillsignal" },
});
