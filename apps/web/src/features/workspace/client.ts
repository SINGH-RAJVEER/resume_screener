const baseURL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export interface Organization {
	id: string;
	name: string;
	role: string;
}

export interface Job {
	id: string;
	title: string;
	versionId: string;
	confirmed: boolean;
}

export interface Requirement {
	id?: string;
	stableId: string;
	text?: string;
	normalizedText?: string;
	kind: "required" | "preferred" | "ignored" | "hard_gate";
	weight: number;
}

export interface JobDetail {
	id: string;
	organizationId: string;
	title: string;
	description: string;
	confirmed: boolean;
	requirements: Requirement[];
	draftRequirements: Array<{ stableId: string; normalizedText: string }>;
}

export interface Evaluation {
	id: string;
	candidateName: string | null;
	candidateEmail: string | null;
	candidateLocation: string | null;
	status: string;
	score: number | null;
	coverage: number | null;
	eligibility: string;
	assessments: Array<{
		requirement: string;
		outcome: string;
		reasoning: string;
		evidence: Array<{ blockId: string; quote: string }>;
	}>;
}

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

export const workspaceClient = {
	organizations: () => request<Organization[]>("/api/organizations"),
	createOrganization: (name: string) =>
		request<Organization>("/api/organizations", {
			method: "POST",
			body: JSON.stringify({ name }),
		}),
	jobs: (organizationId: string) =>
		request<Job[]>(`/api/organizations/${organizationId}/jobs`),
	job: (jobId: string) => request<JobDetail>(`/api/jobs/${jobId}`),
	evaluations: (jobId: string) =>
		request<Evaluation[]>(`/api/jobs/${jobId}/evaluations`),
	createJob: (organizationId: string, title: string, description: string) =>
		request<{ id: string }>("/api/jobs", {
			method: "POST",
			body: JSON.stringify({
				organization_id: organizationId,
				title,
				description,
			}),
		}),
	confirmRequirements: (jobId: string, requirements: Requirement[]) =>
		request<{ confirmed: boolean }>(`/api/jobs/${jobId}/requirements`, {
			method: "POST",
			body: JSON.stringify({
				requirements: requirements.map((requirement) => ({
					stable_id: requirement.stableId,
					normalized_text:
						requirement.normalizedText ?? requirement.text ?? "",
					kind: requirement.kind,
					weight: requirement.weight,
				})),
			}),
		}),
	uploadResume: (jobId: string, file: File) => {
		const body = new FormData();
		body.append("file", file);
		return request<{ processingJobId: string; submissionId: string }>(
			`/api/jobs/${jobId}/resumes`,
			{ method: "POST", body },
		);
	},
	uploadResumes: async (jobId: string, files: File[]) => {
		const results = await Promise.allSettled(
			files.map((file) => workspaceClient.uploadResume(jobId, file)),
		);
		return {
			accepted: results.flatMap((result, index) =>
				result.status === "fulfilled"
					? [{ name: files[index]?.name ?? "resume" }]
					: [],
			),
			rejected: results.flatMap((result, index) =>
				result.status === "rejected"
					? [
							{
								name: files[index]?.name ?? "resume",
								reason:
									result.reason instanceof Error
										? result.reason.message
										: "Upload failed",
							},
						]
					: [],
			),
		};
	},
	uploadResumeBatch: (jobId: string, archive: File) => {
		const body = new FormData();
		body.append("archive", archive);
		return request<{
			accepted: Array<{ name: string }>;
			rejected: Array<{ name: string; reason: string }>;
		}>(`/api/jobs/${jobId}/resume-batches`, { method: "POST", body });
	},
	createInvitation: (jobId: string) =>
		request<{ id: string; token: string; expiresAt: string }>(
			`/api/jobs/${jobId}/invitations`,
			{ method: "POST", body: JSON.stringify({ expires_in_hours: 168 }) },
		),
};
