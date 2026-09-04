const RETRYABLE_STATUS_CODES = new Set([408, 409, 429, 500, 502, 503, 504, 529]);
const RETRYABLE_ERROR_CODES = new Set(["rate_limit_exceeded", "provider_overloaded", "provider_unavailable", "timeout"]);

export class OpenRouterError extends Error {}
export class OpenRouterRetryableError extends OpenRouterError {}

type JsonObject = Record<string, unknown>;

export class OpenRouterClient {
	readonly enabled: boolean;
	private readonly apiKey: string;
	private readonly baseUrl: string;
	private readonly timeoutSeconds: number;
	private promptTokens = 0;
	private completionTokens = 0;
	private costUsd = 0;

	constructor() {
		this.apiKey = Bun.env["OPENROUTER_API_KEY"] ?? "";
		this.baseUrl = (Bun.env["OPENROUTER_BASE_URL"] ?? "https://openrouter.ai/api/v1").replace(/\/+$/, "");
		this.timeoutSeconds = Number(Bun.env["OPENROUTER_TIMEOUT_SECONDS"] ?? 90);
		this.enabled = Boolean(this.apiKey);
	}

	resetUsage(): void {
		this.promptTokens = 0;
		this.completionTokens = 0;
		this.costUsd = 0;
	}

	usage(): { promptTokens: number; completionTokens: number; costUsd: number } {
		return { promptTokens: this.promptTokens, completionTokens: this.completionTokens, costUsd: this.costUsd };
	}

	async completeJson(options: { model: string; systemPrompt: string; userContent: string; schemaName: string; schema: JsonObject; maxOutputTokens: number }): Promise<JsonObject> {
		if (!this.enabled) throw new OpenRouterError("OpenRouter is not configured");
		const body = await this.post("/chat/completions", {
			model: options.model,
			messages: [
				{ role: "system", content: options.systemPrompt },
				{ role: "user", content: options.userContent },
			],
			response_format: { type: "json_schema", json_schema: { name: options.schemaName, strict: true, schema: options.schema } },
			max_tokens: options.maxOutputTokens,
			provider: { require_parameters: true, data_collection: "deny" },
		});
		return parseJsonCompletion(body);
	}

	async complete(model: string, messages: Array<{ role: "system" | "user"; content: string }>, schema?: JsonObject): Promise<{ choices: Array<{ message: { content: string | null } }> }> {
		if (!this.enabled) throw new OpenRouterError("OpenRouter is not configured");
		const payload: JsonObject = { model, messages, temperature: 0 };
		if (schema) payload["response_format"] = { type: "json_schema", json_schema: { name: "skillsignal_output", strict: true, schema } };
		const body = await this.post("/chat/completions", payload);
		const choices = body["choices"];
		if (!Array.isArray(choices) || !choices.length) throw new OpenRouterError("Model response has no choices");
		return body as { choices: Array<{ message: { content: string | null } }> };
	}

	async embed(model: string, input: string[]): Promise<number[][]> {
		return this.embedTexts(model, input);
	}

	async embedTexts(model: string, texts: string[]): Promise<number[][]> {
		if (!this.enabled) throw new OpenRouterError("OpenRouter is not configured");
		const body = await this.post("/embeddings", { model, input: texts });
		return parseEmbeddingResponse(body, texts.length);
	}

	private async post(path: string, payload: JsonObject): Promise<JsonObject> {
		let response: Response;
		try {
			response = await fetch(`${this.baseUrl}${path}`, {
				method: "POST",
				headers: { Authorization: `Bearer ${this.apiKey}`, "Content-Type": "application/json", "X-Title": "skillsignal" },
				body: JSON.stringify(payload),
				signal: AbortSignal.timeout(this.timeoutSeconds * 1000),
			});
		} catch {
			throw new OpenRouterRetryableError("Model request transport failed");
		}
		let body: unknown;
		try {
			body = await response.json();
		} catch {
			throw classifyStatus(response.status, "Model returned invalid JSON");
		}
		if (typeof body !== "object" || body === null || Array.isArray(body)) throw classifyStatus(response.status, "Model response is not an object");
		const record = body as JsonObject;
		if (response.status !== 200) {
			const error = record["error"];
			const message = typeof error === "object" && error !== null ? String((error as JsonObject)["message"] ?? "") : "";
			throw classifyStatus(response.status, message || `HTTP ${response.status}`);
		}
		if (typeof record["error"] === "object" && record["error"] !== null) throw classifyError(record["error"] as JsonObject);
		this.recordUsage(record);
		return record;
	}

	private recordUsage(body: JsonObject): void {
		const usage = body["usage"];
		if (typeof usage !== "object" || usage === null) return;
		const record = usage as JsonObject;
		if (typeof record["prompt_tokens"] === "number") this.promptTokens += record["prompt_tokens"];
		if (typeof record["completion_tokens"] === "number") this.completionTokens += record["completion_tokens"];
		if (typeof record["cost"] === "number") this.costUsd += record["cost"];
	}
}

export const classifyStatus = (status: number, message: string): OpenRouterError => {
	if (RETRYABLE_STATUS_CODES.has(status)) return new OpenRouterRetryableError(message);
	if (status === 402) return new OpenRouterError("Model credits are exhausted");
	if (status === 401 || status === 403) return new OpenRouterError("Model credentials were rejected");
	return new OpenRouterError(message);
};

export const classifyError = (error: JsonObject): OpenRouterError => {
	const code = typeof error["code"] === "string" ? error["code"] : "";
	const message = typeof error["message"] === "string" && error["message"] ? error["message"] : code;
	const metadata = error["metadata"];
	if (typeof metadata === "object" && metadata !== null && (metadata as JsonObject)["file_annotations"]) {
		return new OpenRouterError(message || "Provider failed");
	}
	if (RETRYABLE_ERROR_CODES.has(code)) return new OpenRouterRetryableError(message || code);
	return new OpenRouterError(message || "Provider failed");
};

export const parseEmbeddingResponse = (body: JsonObject, expectedCount: number): number[][] => {
	const data = body["data"];
	if (!Array.isArray(data) || !data.length) throw new OpenRouterError("Embedding response has no data");
	const vectors = new Map<number, number[]>();
	for (const item of data) {
		if (typeof item !== "object" || item === null) throw new OpenRouterError("Embedding entry is malformed");
		const entry = item as JsonObject;
		const index = entry["index"];
		const embedding = entry["embedding"];
		if (typeof index !== "number" || !Number.isInteger(index) || index < 0 || index >= expectedCount) {
			throw new OpenRouterError("Embedding response indexes do not match the request");
		}
		if (vectors.has(index)) throw new OpenRouterError("Embedding response repeats an input index");
		if (!Array.isArray(embedding) || !embedding.length || !embedding.every((value) => typeof value === "number")) {
			throw new OpenRouterError("Embedding vector is missing");
		}
		vectors.set(index, embedding as number[]);
	}
	if (vectors.size !== expectedCount) throw new OpenRouterError("Embedding response does not cover every input");
	const dimensions = new Set([...vectors.values()].map((vector) => vector.length));
	if (dimensions.size !== 1) throw new OpenRouterError("Embedding vectors have inconsistent dimensions");
	return Array.from({ length: expectedCount }, (_, index) => vectors.get(index) as number[]);
};

export const parseJsonCompletion = (body: JsonObject): JsonObject => {
	const choices = body["choices"];
	if (!Array.isArray(choices) || !choices.length) throw new OpenRouterError("Model response has no choices");
	const first = choices[0];
	if (typeof first !== "object" || first === null) throw new OpenRouterError("Model response choice is malformed");
	const choice = first as JsonObject;
	const finishReason = choice["finish_reason"];
	if (finishReason === "length") throw new OpenRouterRetryableError("Model output was truncated");
	if (finishReason !== "stop" && finishReason !== null && finishReason !== undefined) {
		throw new OpenRouterError(`Model stopped early: ${String(finishReason)}`);
	}
	const message = choice["message"];
	let content = "";
	let refusal = "";
	if (typeof message === "object" && message !== null) {
		const record = message as JsonObject;
		if (typeof record["content"] === "string") content = record["content"];
		if (typeof record["refusal"] === "string") refusal = record["refusal"];
	}
	if (!content.trim()) {
		if (refusal) throw new OpenRouterError("Model refused the extraction request");
		throw new OpenRouterError("Model response is empty");
	}
	let parsed: unknown;
	try {
		parsed = JSON.parse(content);
	} catch {
		throw new OpenRouterError("Model response is not valid JSON");
	}
	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
		throw new OpenRouterError("Model response is not a JSON object");
	}
	return parsed as JsonObject;
};
