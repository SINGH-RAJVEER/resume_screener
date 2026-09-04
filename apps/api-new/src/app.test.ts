import { describe, expect, test } from "bun:test";
import type { Database } from "@skillsignal/server-core/db";
import { createApp } from "./app.ts";

describe("Hono API", () => {
	test("serves the health contract without a database query", async () => {
		const app = createApp({} as Database, {
			databaseUrl: "postgres://unused",
			storageRoot: ".local-storage",
			webUrl: "http://localhost:3000",
			jwtSecret: "x".repeat(32),
			jwtTtlSeconds: 3600,
			retentionSweepIntervalSeconds: 0,
			workerPollIntervalSeconds: 1,
			workerLeaseSeconds: 60,
			parseTimeoutSeconds: 30,
			independentRetentionDays: 30,
			openrouter: { apiKey: "", baseUrl: "https://openrouter.ai/api/v1", timeoutSeconds: 90, extractionModels: [], assessmentModels: [], embeddingModels: [], embeddingModel: "openai/text-embedding-3-small" },
		});
		const response = await app.request("http://localhost/health");
		expect(response.status).toBe(200);
		expect(await response.json()).toEqual({ status: "ok" });
	});
});
