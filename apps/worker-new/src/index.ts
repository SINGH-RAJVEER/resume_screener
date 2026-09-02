import { createDatabase } from "@skillsignal/server-core/db";
import { loadConfig } from "@skillsignal/server-core/config";
import { Worker } from "./worker.ts";

const config = loadConfig();
const { db, client } = createDatabase(config.databaseUrl);
const worker = new Worker(db, config.workerPollIntervalSeconds, config.workerLeaseSeconds, config.storageRoot);
process.once("SIGINT", () => worker.stop());
process.once("SIGTERM", () => worker.stop());
try {
	await worker.run();
} finally {
	await client.end();
}
