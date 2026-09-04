import { createHmac, timingSafeEqual } from "node:crypto";

export class RazorpayError extends Error {}

export class RazorpayUnavailableError extends RazorpayError {}

const signaturesEqual = (expected: string, actual: string): boolean => {
	const expectedBytes = Buffer.from(expected, "utf8");
	const actualBytes = Buffer.from(actual, "utf8");
	return expectedBytes.length === actualBytes.length && timingSafeEqual(expectedBytes, actualBytes);
};

export const verifyCheckoutSignature = (orderId: string, paymentId: string, signature: string, keySecret: string): boolean => {
	const expected = createHmac("sha256", keySecret).update(`${orderId}|${paymentId}`).digest("hex");
	return signaturesEqual(expected, signature);
};

export const verifyWebhookSignature = (body: Uint8Array, signature: string, webhookSecret: string): boolean => {
	const expected = createHmac("sha256", webhookSecret).update(body).digest("hex");
	return signaturesEqual(expected, signature);
};

type RazorpayBody = Record<string, unknown>;

const isObject = (value: unknown): value is RazorpayBody => typeof value === "object" && value !== null && !Array.isArray(value);

export class RazorpayClient {
	private readonly authorization: string;
	private readonly baseUrl: string;
	private readonly timeoutMilliseconds: number;

	public constructor(keyId: string, keySecret: string, baseUrl = "https://api.razorpay.com/v1", timeoutSeconds = 15) {
		if (!keyId || !keySecret) throw new RazorpayUnavailableError("Razorpay credentials are not configured");
		this.authorization = `Basic ${Buffer.from(`${keyId}:${keySecret}`).toString("base64")}`;
		this.baseUrl = baseUrl.replace(/\/+$/, "");
		this.timeoutMilliseconds = timeoutSeconds * 1000;
	}

	public async createOrder(amountPaise: number, currency: string, receipt: string, notes?: Record<string, string>): Promise<RazorpayBody> {
		const body = await this.request("POST", "/orders", {
			amount: amountPaise,
			currency,
			receipt,
			notes: notes ?? {},
		});
		if (typeof body["id"] !== "string") throw new RazorpayError("Razorpay order response is missing an identifier");
		return body;
	}

	public async orderPayments(razorpayOrderId: string): Promise<RazorpayBody[]> {
		const body = await this.request("GET", `/orders/${razorpayOrderId}/payments`);
		if (!Array.isArray(body["items"])) throw new RazorpayError("Razorpay payments response is malformed");
		return body["items"].filter(isObject);
	}

	private async request(method: string, path: string, requestBody?: RazorpayBody): Promise<RazorpayBody> {
		const controller = new AbortController();
		const timeout = setTimeout(() => controller.abort(), this.timeoutMilliseconds);
		let response: Response;
		try {
			response = await fetch(`${this.baseUrl}${path}`, {
				method,
				headers: { Authorization: this.authorization, ...(requestBody ? { "Content-Type": "application/json" } : {}) },
				...(requestBody ? { body: JSON.stringify(requestBody) } : {}),
				signal: controller.signal,
			});
		} catch (cause) {
			throw new RazorpayUnavailableError("Razorpay request failed", { cause });
		} finally {
			clearTimeout(timeout);
		}

		let body: unknown;
		try {
			body = await response.json();
		} catch (cause) {
			throw new RazorpayError(`Razorpay returned invalid JSON (${response.status})`, { cause });
		}
		if (!isObject(body)) throw new RazorpayError("Razorpay returned an unexpected response shape");
		if (!response.ok) {
			const error = body["error"];
			const description = isObject(error) && typeof error["description"] === "string" ? error["description"] : "";
			throw new RazorpayError(description || `Razorpay returned HTTP ${response.status}`);
		}
		return body;
	}
}

export const paymentEntity = (payload: RazorpayBody): RazorpayBody => {
	const payloadValue = payload["payload"];
	const paymentValue = isObject(payloadValue) ? payloadValue["payment"] : undefined;
	return isObject(paymentValue) && isObject(paymentValue["entity"]) ? paymentValue["entity"] : {};
};

export const refundEntities = (payment: RazorpayBody): RazorpayBody[] => Array.isArray(payment["refunds"]) ? payment["refunds"].filter(isObject) : [];
