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
	redeemInvitation: (token: string) =>
		request<{ jobId: string; invitationId: string }>(
			`/api/invitations/${token}/redeem`,
			{ method: "POST" },
		),
	uploadInvitedResume: (
		jobId: string,
		token: string,
		file: File,
		candidateName: string,
	) => {
		const body = new FormData();
		body.append("file", file);
		body.append("candidate_name", candidateName);
		body.append("invitation_token", token);
		return request<{ processingJobId: string; submissionId: string }>(
			`/api/jobs/${jobId}/resumes`,
			{ method: "POST", body },
		);
	},
};
