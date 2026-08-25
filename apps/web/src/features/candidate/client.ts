const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
	const response = await fetch(`${baseURL}${path}`, {
		...init,
		headers: {
			...(init?.body instanceof FormData
				? {}
				: { "Content-Type": "application/json" }),
			Authorization: `Bearer ${localStorage.getItem("auth_token") ?? ""}`,
			...init?.headers,
		},
	});
	const body =
		response.status === 204
			? undefined
			: ((await response.json()) as T & { message?: string });
	if (!response.ok) throw new Error(body?.message ?? "Request failed");
	return body as T;
};

export const candidateClient = {
	createIndependentEvaluation: (
		file: File,
		jobDescription: string,
		jobDescriptionFile?: File | null,
	) => {
		const body = new FormData();
		body.append("file", file);
		body.append("job_description", jobDescription);
		if (jobDescriptionFile)
			body.append("job_description_file", jobDescriptionFile);
		return request<{ id: string; processingJobId: string }>(
			"/api/independent-evaluations",
			{ method: "POST", body },
		);
	},
	independentEvaluation: (evaluationId: string) =>
		request<IndependentEvaluation>(
			`/api/independent-evaluations/${evaluationId}`,
		),
	downloadImprovedResume: async (evaluationId: string) => {
		const response = await fetch(
			`${baseURL}/api/independent-evaluations/${evaluationId}/improved-resume`,
			{
				headers: {
					Authorization: `Bearer ${localStorage.getItem("auth_token") ?? ""}`,
				},
			},
		);
		if (!response.ok) throw new Error("Corrected resume is not available");
		const blob = await response.blob();
		const url = URL.createObjectURL(blob);
		const anchor = document.createElement("a");
		anchor.href = url;
		anchor.download = "corrected-resume.docx";
		anchor.click();
		URL.revokeObjectURL(url);
	},
	independentEvaluations: () =>
		request<IndependentEvaluation[]>("/api/independent-evaluations"),
	deleteIndependentEvaluation: (evaluationId: string) =>
		request<void>(`/api/independent-evaluations/${evaluationId}`, {
			method: "DELETE",
		}),
	redeemInvitation: (token: string) =>
		request<{ jobId: string; invitationId: string }>(
			`/api/invitations/${token}/redeem`,
			{ method: "POST" },
		),
	redeemPasscode: (passcode: string) =>
		request<{ jobId: string; invitationId: string }>(
			"/api/invitations/redeem",
			{
				method: "POST",
				body: JSON.stringify({ passcode }),
			},
		),
	points: () => request<PointsSummary>("/api/me/points"),
	packs: () => request<PointPack[]>("/api/billing/packs"),
	quote: () =>
		request<PointQuote>("/api/billing/quote?kind=independent_evaluation"),
	createOrder: (packId: string) =>
		request<OrderResponse>("/api/billing/orders", {
			method: "POST",
			body: JSON.stringify({ pack_id: packId }),
		}),
	verifyCheckout: (
		orderId: string,
		razorpayPaymentId: string,
		razorpaySignature: string,
	) =>
		request<{ verified: boolean }>(
			`/api/billing/orders/${orderId}/verify`,
			{
				method: "POST",
				body: JSON.stringify({
					razorpay_payment_id: razorpayPaymentId,
					razorpay_signature: razorpaySignature,
				}),
			},
		),
	uploadInvitedResume: (jobId: string, token: string, file: File) => {
		const body = new FormData();
		body.append("file", file);
		body.append("invitation_token", token);
		return request<{
			processingJobId: string;
			submissionId: string;
			evaluationId: string;
		}>(`/api/jobs/${jobId}/resumes`, { method: "POST", body });
	},
};

export type PointPack = { id: string; points: number; amountInr: number };

export type OrderResponse = {
	id: string;
	razorpayOrderId: string;
	razorpayKeyId: string;
	amountInr: number;
	currency: string;
	packId: string;
	points: number;
};

export type PointsSummary = {
	scope: string;
	balance: number;
	available: number;
	allowance?: {
		freeUsedThisWeek: boolean;
		resetsAt: string;
	};
};

export type PointQuote = {
	kind: string;
	points: number;
	minimumPoints: number;
	costCeilingPoints: number;
	lineItems: Array<{
		task: string;
		maxInputTokens: number;
		maxOutputTokens: number;
	}>;
};

export type SkillFact = {
	canonicalName: string;
	category?: string | null;
};

export type EmploymentFact = {
	employer?: string | null;
	title?: string | null;
	startDate?: string | null;
	endDate?: string | null;
	isCurrent?: boolean;
};

export type EducationFact = {
	institution?: string | null;
	degree?: string | null;
	fieldOfStudy?: string | null;
	graduationDate?: string | null;
};

export type CertificationFact = { name: string; issuer?: string | null };

export type IndependentEvaluation = {
	id: string;
	originalName: string;
	status: "queued" | "processing" | "complete" | "failed";
	score: number | null;
	safeError: string | null;
	createdAt: string;
	completedAt: string | null;
	jobDescriptionProvided?: boolean;
	hasImprovedResume?: boolean;
	suggestions?: Array<{ title: string; detail: string }>;
	facts?: {
		skills?: SkillFact[];
		employment?: EmploymentFact[];
		education?: EducationFact[];
		certifications?: CertificationFact[];
		warnings?: string[];
	};
};
