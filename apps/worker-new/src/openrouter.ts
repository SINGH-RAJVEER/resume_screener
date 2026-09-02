import { z } from "zod";

const completion = z.object({
	id: z.string(), model: z.string(), choices: z.array(z.object({ message: z.object({ content: z.string().nullable() }), finish_reason: z.string().nullable() })),
	usage: z.object({ prompt_tokens: z.number().optional(), completion_tokens: z.number().optional(), cost: z.number().optional() }).optional(),
});

export class OpenRouterClient {
	readonly enabled: boolean;
	private readonly key: string;
	private readonly baseUrl: string;

	constructor() {
		this.key = Bun.env["OPENROUTER_API_KEY"] ?? "";
		this.baseUrl = Bun.env["OPENROUTER_BASE_URL"] ?? "https://openrouter.ai/api/v1";
		this.enabled = Boolean(this.key);
	}

	async complete(model: string, messages: Array<{ role: "system" | "user"; content: string }>, schema?: Record<string, unknown>): Promise<z.infer<typeof completion>> {
		if (!this.enabled) throw new Error("OpenRouter is not configured");
		const body: Record<string, unknown> = { model, messages, temperature: 0 };
		if (schema) body["response_format"] = { type: "json_schema", json_schema: { name: "skillsignal_output", strict: true, schema } };
		const response = await fetch(`${this.baseUrl}/chat/completions`, { method: "POST", headers: { Authorization: `Bearer ${this.key}`, "Content-Type": "application/json", "X-OpenRouter-Metadata": "enabled" }, body: JSON.stringify(body), signal: AbortSignal.timeout(Number(Bun.env["OPENROUTER_TIMEOUT_SECONDS"] ?? 90) * 1000) });
		if (!response.ok) throw new Error(`OpenRouter request failed: ${response.status}`);
		return completion.parse(await response.json());
	}

	async embed(model: string, input: string[]): Promise<number[][]> {
		if (!this.enabled) throw new Error("OpenRouter is not configured");
		const response = await fetch(`${this.baseUrl}/embeddings`, { method: "POST", headers: { Authorization: `Bearer ${this.key}`, "Content-Type": "application/json" }, body: JSON.stringify({ model, input }), signal: AbortSignal.timeout(Number(Bun.env["OPENROUTER_TIMEOUT_SECONDS"] ?? 90) * 1000) });
		if (!response.ok) throw new Error(`OpenRouter embedding failed: ${response.status}`);
		const payload = z.object({ data: z.array(z.object({ embedding: z.array(z.number()) })) }).parse(await response.json());
		return payload.data.map((item) => item.embedding);
	}
}
