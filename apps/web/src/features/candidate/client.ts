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
	const body = (await response.json()) as T & { message?: string };
	if (!response.ok) throw new Error(body.message ?? "Request failed");
	return body;
};

export const candidateClient = {
	createIndependentEvaluation: (file: File, jobDescription: string) => {
		const body = new FormData();
		body.append("file", file);
		body.append("job_description", jobDescription);
		return request<{ id: string; processingJobId: string }>(
			"/api/independent-evaluations",
			{ method: "POST", body },
		);
	},
	independentEvaluation: (evaluationId: string) =>
		request<IndependentEvaluation>(
			`/api/independent-evaluations/${evaluationId}`,
		),
	independentEvaluations: () =>
		request<IndependentEvaluation[]>("/api/independent-evaluations"),
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
	uploadInvitedResume: (jobId: string, token: string, file: File) => {
		const body = new FormData();
		body.append("file", file);
		body.append("invitation_token", token);
		return request<{ processingJobId: string; submissionId: string }>(
			`/api/jobs/${jobId}/resumes`,
			{ method: "POST", body },
		);
	},
};

export type IndependentEvaluation = {
	id: string;
	originalName: string;
	status: "queued" | "processing" | "complete" | "failed";
	score: number | null;
	safeError: string | null;
	createdAt: string;
	completedAt: string | null;
	jobDescriptionProvided?: boolean;
	suggestions?: Array<{ title: string; detail: string }>;
	facts?: {
		skills?: Array<{ canonicalName: string }>;
	};
};
