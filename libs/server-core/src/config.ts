export type ServerConfig = {
	databaseUrl: string;
	storageRoot: string;
	webUrl: string;
	jwtSecret: string;
	jwtTtlSeconds: number;
	retentionSweepIntervalSeconds: number;
	workerPollIntervalSeconds: number;
	workerLeaseSeconds: number;
	parseTimeoutSeconds: number;
};

const required = (name: string): string => {
	const value = Bun.env[name];
	if (!value) throw new Error(`${name} is required`);
	return value;
};

const integer = (name: string, fallback: number): number => {
	const value = Number(Bun.env[name] ?? fallback);
	if (!Number.isInteger(value) || value < 0) throw new Error(`${name} must be a non-negative integer`);
	return value;
};

const duration = (value: string): number => {
	const match = /^([0-9]+(?:\.[0-9]+)?)(ms|s|m|h)$/.exec(value);
	if (!match) throw new Error("JWT_TTL must be a positive duration");
	const amount = Number(match[1]);
	const multiplier = { ms: 0.001, s: 1, m: 60, h: 3600 }[match[2] as "ms" | "s" | "m" | "h"];
	return amount * multiplier;
};

export const loadConfig = (): ServerConfig => {
	const jwtSecret = required("JWT_SECRET");
	if (jwtSecret.length < 32) throw new Error("JWT_SECRET must be at least 32 characters");
	return {
		databaseUrl: Bun.env["DATABASE_URL"] ?? "postgres://postgres:password@localhost:5432/skillsignal",
		storageRoot: Bun.env["STORAGE_ROOT"] ?? ".local-storage",
		webUrl: Bun.env["WEB_URL"] ?? "http://localhost:3000",
		jwtSecret,
		jwtTtlSeconds: duration(Bun.env["JWT_TTL"] ?? "168h"),
		retentionSweepIntervalSeconds: integer("RETENTION_SWEEP_INTERVAL_SECONDS", 3600),
		workerPollIntervalSeconds: integer("WORKER_POLL_INTERVAL_SECONDS", 2),
		workerLeaseSeconds: integer("WORKER_LEASE_SECONDS", 60),
		parseTimeoutSeconds: integer("PARSE_TIMEOUT_SECONDS", 30),
	};
};
