export const telemetryEnabled = (): boolean =>
	Boolean(Bun.env["OTEL_EXPORTER_OTLP_ENDPOINT"]) && (Bun.env["OTEL_SDK_DISABLED"] ?? "").toLowerCase() !== "true";

export const setupTelemetry = (): boolean => {
	if (!telemetryEnabled()) return false;
	console.info("OpenTelemetry exporter configured; Bun runtime uses console spans");
	return true;
};

export const recordJobOutcome = (jobType: string, outcome: string, durationSeconds: number): void => {
	if (Bun.env["WORKER_TELEMETRY_VERBOSE"] === "1") console.info("worker job finished", { jobType, outcome, durationSeconds });
};
