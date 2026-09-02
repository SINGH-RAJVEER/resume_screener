export type RazorpayPack = {
	readonly id: string;
	readonly points: number;
	readonly amountInr: number;
};

export type TaskBudget = {
	readonly task: string;
	readonly maxInputTokens: number;
	readonly maxOutputTokens: number;
};

export type BillingSettings = {
	readonly pointsPerUsd: number;
	readonly minimumIndependentEvaluationPoints: number;
	readonly minimumEmployerResumePoints: number;
	readonly priceCeilingUsdPerMillionInput: number;
	readonly priceCeilingUsdPerMillionOutput: number;
	readonly independentBudgets: readonly TaskBudget[];
	readonly employerBudgets: readonly TaskBudget[];
	readonly packs: readonly RazorpayPack[];
	readonly razorpayKeyId: string;
	readonly razorpayKeySecret: string;
	readonly razorpayWebhookSecret: string;
	readonly adminToken: string;
	readonly enterpriseSalesEmail: string;
};

const defaultPacks = (): RazorpayPack[] => [
	{ id: "pack-500", points: 500, amountInr: 499 },
	{ id: "pack-2000", points: 2000, amountInr: 1499 },
];

const integerEnv = (name: string, fallback: number): number => {
	const raw = Bun.env[name];
	if (raw === undefined || raw === "") return fallback;
	const value = Number(raw);
	if (!Number.isInteger(value) || value < 0) throw new Error(`${name} must be a non-negative integer`);
	return value;
};

const floatEnv = (name: string, fallback: number): number => {
	const raw = Bun.env[name];
	if (raw === undefined || raw === "") return fallback;
	const value = Number(raw);
	if (!Number.isFinite(value) || value < 0) throw new Error(`${name} must be a non-negative number`);
	return value;
};

export const loadPacks = (): RazorpayPack[] => {
	const raw = Bun.env["RAZORPAY_PACKS"] ?? "";
	if (!raw.trim()) return defaultPacks();
	let parsed: unknown;
	try {
		parsed = JSON.parse(raw);
	} catch {
		throw new Error("RAZORPAY_PACKS must be valid JSON");
	}
	if (!Array.isArray(parsed)) throw new Error("RAZORPAY_PACKS must be a JSON array of packs");
	const packs = parsed.map((entry) => {
		if (typeof entry !== "object" || entry === null) throw new Error("Each Razorpay pack must be a JSON object");
		const record = entry as Record<string, unknown>;
		const pack = { id: String(record["id"]), points: Number(record["points"] ?? record["points"]), amountInr: Number(record["amountInr"] ?? record["amount_inr"]) };
		if (!pack.id || !Number.isInteger(pack.points) || pack.points <= 0 || !Number.isInteger(pack.amountInr) || pack.amountInr <= 0) {
			throw new Error("Razorpay pack points and amount must be positive");
		}
		return pack;
	});
	if (!packs.length) throw new Error("RAZORPAY_PACKS must define at least one pack");
	return packs;
};

export const loadBillingSettings = (): BillingSettings => ({
	pointsPerUsd: integerEnv("POINTS_PER_USD", 1000),
	minimumIndependentEvaluationPoints: integerEnv("MIN_POINTS_INDEPENDENT_EVALUATION", 10),
	minimumEmployerResumePoints: integerEnv("MIN_POINTS_EMPLOYER_RESUME", 5),
	priceCeilingUsdPerMillionInput: floatEnv("PRICE_CEILING_INPUT_USD_PER_MILLION", 3),
	priceCeilingUsdPerMillionOutput: floatEnv("PRICE_CEILING_OUTPUT_USD_PER_MILLION", 15),
	independentBudgets: [{ task: "extraction", maxInputTokens: integerEnv("QUOTE_EXTRACTION_INPUT_TOKENS", 16000), maxOutputTokens: integerEnv("QUOTE_EXTRACTION_OUTPUT_TOKENS", 4096) }],
	employerBudgets: [
		{ task: "extraction", maxInputTokens: integerEnv("QUOTE_EXTRACTION_INPUT_TOKENS", 16000), maxOutputTokens: integerEnv("QUOTE_EXTRACTION_OUTPUT_TOKENS", 4096) },
		{ task: "assessment", maxInputTokens: integerEnv("QUOTE_ASSESSMENT_INPUT_TOKENS", 24000), maxOutputTokens: integerEnv("QUOTE_ASSESSMENT_OUTPUT_TOKENS", 4096) },
		{ task: "embedding", maxInputTokens: integerEnv("QUOTE_EMBEDDING_INPUT_TOKENS", 32000), maxOutputTokens: 0 },
	],
	packs: loadPacks(),
	razorpayKeyId: Bun.env["RAZORPAY_KEY_ID"] ?? "",
	razorpayKeySecret: Bun.env["RAZORPAY_KEY_SECRET"] ?? "",
	razorpayWebhookSecret: Bun.env["RAZORPAY_WEBHOOK_SECRET"] ?? "",
	adminToken: Bun.env["ADMIN_TOKEN"] ?? "",
	enterpriseSalesEmail: Bun.env["ENTERPRISE_SALES_EMAIL"] ?? "sales@skillsignal.app",
});

export const findPack = (settings: BillingSettings, packId: string): RazorpayPack | null =>
	settings.packs.find((pack) => pack.id === packId) ?? null;
