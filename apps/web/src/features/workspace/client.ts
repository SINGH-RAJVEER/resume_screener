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
	status: string;
	score: number | null;
	coverage: number | null;
	eligibility: string;
	assessments: Array<{
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
			body: JSON.stringify({ organizationId, title, description }),
		}),
	confirmRequirements: (jobId: string, requirements: Requirement[]) =>
		request<{ confirmed: boolean }>(`/api/jobs/${jobId}/requirements`, {
			method: "POST",
			body: JSON.stringify({
				requirements: requirements.map((requirement) => ({
					stableId: requirement.stableId,
					normalizedText:
						requirement.normalizedText ?? requirement.text ?? "",
					kind: requirement.kind,
					weight: requirement.weight,
				})),
			}),
		}),
	uploadResume: (jobId: string, file: File, candidateName: string) => {
		const body = new FormData();
		body.append("file", file);
		body.append("candidate_name", candidateName);
		return request<{ processingJobId: string; submissionId: string }>(
			`/api/jobs/${jobId}/resumes`,
			{ method: "POST", body },
		);
	},
	processingJob: (processingJobId: string) =>
		request<{ id: string; status: string; safeError: string | null }>(
			`/api/processing-jobs/${processingJobId}`,
		),
};
