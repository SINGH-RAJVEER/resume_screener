import { bootstrap } from "./app.ts";
import { createDatabase } from "@skillsignal/server-core/db";
import { purgeExpiredData } from "@skillsignal/server-core/retention";
import { LocalObjectStorage } from "@skillsignal/server-core/storage";

const { app, config } = bootstrap();

if (config.retentionSweepIntervalSeconds > 0) {
	const sweep = async (): Promise<void> => {
		try {
			const { db, client } = createDatabase(config.databaseUrl);
			try {
				await purgeExpiredData(db, new LocalObjectStorage(config.storageRoot), new Date());
			} finally {
				await client.end();
			}
		} catch (cause) {
			console.error("retention sweep failed", { name: (cause as Error).name });
		}
	};
	const timer = setInterval(() => { void sweep(); }, config.retentionSweepIntervalSeconds * 1000);
	timer.unref?.();
}

const port = Number(Bun.env["PORT"] ?? 8000);
console.log(`SkillSignal API listening on ${port}`);
Bun.serve({ port, fetch: app.fetch });
