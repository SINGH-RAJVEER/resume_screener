import { downloadFile, apiRequest as request } from "../../lib/api-client";
import type {
	OrderResponse,
	PointPack,
	PointsSummary,
} from "../../lib/billing-types";

export type { OrderResponse, PointPack, PointsSummary };

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
	category?: string;
	sourceModality?: string;
	assessability?: string;
	predicate?: {
		operator: "all_of" | "any_of";
		criteria: Array<{
			type: string;
			canonicalName?: string | null;
			minimumMonths?: number | null;
			minimumLevel?: string | null;
			subjects?: string[];
		}>;
	};
	evidence?: RequirementEvidence[];
	sourceEvidence?: RequirementEvidence[];
	confidence?: number;
}

export interface RequirementEvidence {
	blockId: string;
	quote: string;
	startOffset?: number;
	endOffset?: number;
	section?: string;
}

export interface DraftRequirement extends Omit<Requirement, "kind" | "weight"> {
	suggestedKind: "required" | "preferred" | "ignored";
	suggestedWeight: number;
}

export interface JobDetail {
	id: string;
	organizationId: string;
	title: string;
	description: string | null;
	confirmed: boolean;
	applicationOpensAt: string | null;
	applicationClosesAt: string | null;
	draftStatus: "processing" | "ready" | "failed";
	draftError: string | null;
	draftQualityState: "ready" | "review_required" | null;
	draftWarnings: string[];
	draftDegraded: boolean;
	requirements: Requirement[];
	draftRequirements: DraftRequirement[];
}

export interface Member {
	userId: string;
	name: string;
	email: string;
	role: "owner" | "recruiter" | "viewer";
}

export interface JoinPolicy {
	defaultRole: "recruiter" | "viewer";
	domains: string[];
	emails: string[];
}

export interface Evaluation {
	id: string;
	candidateName: string | null;
	candidateEmail: string | null;
	candidateLocation: string | null;
	status: string;
	score: number | null;
	coverage: number | null;
	eligibility: "pending" | "eligible" | "needs_review" | "not_eligible";
	qualityState?: "pending" | "ready" | "review_required" | "failed";
	qualityWarnings?: string[];
	extractionMetadata?: {
		mediaType?: string;
		pageCount?: number;
		blockCount?: number;
		characterCount?: number;
		nonWhitespaceCharacterCount?: number;
	};
	skills?: string[];
	hardGates?: Array<{ requirement: string; outcome: string }>;
	assessments: Array<{
		requirement: string;
		outcome: "met" | "partial" | "not_met" | "unknown";
		kind?: string;
		weight?: number;
		contribution?: number | null;
		reasoning: string;
		evidence: Array<{ blockId: string; quote: string }>;
		semanticEvidence?: {
			model: string;
			matches: Array<{
				blockId: string;
				similarity: number;
				text?: string;
			}>;
		} | null;
		lexicalEvidence?: {
			matches: Array<{
				blockId: string;
				similarity: number;
				text?: string;
			}>;
		} | null;
	}>;
}

export interface EvaluationFilters {
	eligibility?: Evaluation["eligibility"][];
	minimumScore?: number;
	minimumCoverage?: number;
	status?: string[];
	outcome?: string[];
	search?: string;
	skill?: string;
}

export const EXPORT_COLUMNS = [
	"candidate_name",
	"candidate_email",
	"candidate_location",
	"status",
	"score",
	"eligibility",
	"evidence_coverage",
	"quality_state",
	"quality_warnings",
] as const;

export type ExportColumn = (typeof EXPORT_COLUMNS)[number];

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
	evaluations: (jobId: string, filters: EvaluationFilters = {}) => {
		const params = new URLSearchParams();
		for (const value of filters.eligibility ?? []) {
			params.append("eligibility", value);
		}
		for (const value of filters.status ?? []) {
			params.append("status", value);
		}
		for (const value of filters.outcome ?? []) {
			params.append("outcome", value);
		}
		if (filters.minimumScore !== undefined) {
			params.set("minimum_score", String(filters.minimumScore));
		}
		if (filters.minimumCoverage !== undefined) {
			params.set("minimum_coverage", String(filters.minimumCoverage));
		}
		if (filters.search?.trim()) {
			params.set("search", filters.search.trim());
		}
		if (filters.skill?.trim()) {
			params.set("skill", filters.skill.trim());
		}
		const query = params.size ? `?${params.toString()}` : "";
		return request<Evaluation[]>(`/api/jobs/${jobId}/evaluations${query}`);
	},
	exportEvaluationsCsv: async (
		jobId: string,
		exportOptions: { columns?: ExportColumn[]; labels?: string[] } = {},
	) => {
		const params = new URLSearchParams();
		for (const column of exportOptions.columns ?? []) {
			params.append("columns", column);
		}
		for (const label of exportOptions.labels ?? []) {
			params.append("labels", label);
		}
		const query = params.size ? `?${params.toString()}` : "";
		await downloadFile(
			`/api/jobs/${jobId}/evaluations.csv${query}`,
			"evaluations.csv",
			"Export failed",
		);
	},
	createJob: (
		organizationId: string,
		title: string,
		description: string,
		descriptionFile?: File | null,
	) => {
		const body = new FormData();
		body.append("organization_id", organizationId);
		body.append("title", title);
		body.append("description", description);
		if (descriptionFile) body.append("file", descriptionFile);
		return request<{
			id: string;
			versionId: string;
			processingJobId: string;
		}>("/api/jobs", { method: "POST", body });
	},
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
	uploadResumeBatch: (jobId: string, archive: File) => {
		const body = new FormData();
		body.append("archive", archive);
		return request<{
			accepted: Array<{ name: string }>;
			rejected: Array<{ name: string; reason: string }>;
		}>(`/api/jobs/${jobId}/resume-batches`, { method: "POST", body });
	},
	uploadResumeFiles: (jobId: string, files: File[]) => {
		const body = new FormData();
		for (const file of files) {
			body.append("files", file);
		}
		return request<{
			accepted: Array<{ name: string }>;
			rejected: Array<{ name: string; reason: string }>;
		}>(`/api/jobs/${jobId}/resume-batches/files`, { method: "POST", body });
	},
	createInvitation: (jobId: string, expiresInHours = 168) =>
		request<{
			id: string;
			token: string;
			passcode: string;
			expiresAt: string;
		}>(`/api/jobs/${jobId}/invitations`, {
			method: "POST",
			body: JSON.stringify({ expires_in_hours: expiresInHours }),
		}),
	setApplicationWindow: (jobId: string, opensAt: string, closesAt: string) =>
		request<{ opensAt: string; closesAt: string }>(
			`/api/jobs/${jobId}/application-window`,
			{
				method: "PUT",
				body: JSON.stringify({
					opens_at: opensAt,
					closes_at: closesAt,
				}),
			},
		),
	members: (organizationId: string) =>
		request<Member[]>(`/api/organizations/${organizationId}/members`),
	addMember: (organizationId: string, email: string, role: Member["role"]) =>
		request<{ userId: string; role: string }>(
			`/api/organizations/${organizationId}/members`,
			{
				method: "POST",
				body: JSON.stringify({ email, role }),
			},
		),
	removeMember: (organizationId: string, userId: string) =>
		request<void>(
			`/api/organizations/${organizationId}/members/${userId}`,
			{
				method: "DELETE",
			},
		),
	joinPolicy: (organizationId: string) =>
		request<JoinPolicy>(`/api/organizations/${organizationId}/join-policy`),
	setJoinPolicyDefaultRole: (
		organizationId: string,
		defaultRole: JoinPolicy["defaultRole"],
	) =>
		request<{ defaultRole: string }>(
			`/api/organizations/${organizationId}/join-policy`,
			{
				method: "PUT",
				body: JSON.stringify({ default_role: defaultRole }),
			},
		),
	addJoinPolicyDomain: (organizationId: string, domain: string) =>
		request<{ domain: string }>(
			`/api/organizations/${organizationId}/join-policy/domains`,
			{ method: "POST", body: JSON.stringify({ domain }) },
		),
	removeJoinPolicyDomain: (organizationId: string, domain: string) =>
		request<void>(
			`/api/organizations/${organizationId}/join-policy/domains/${encodeURIComponent(domain)}`,
			{ method: "DELETE" },
		),
	addJoinPolicyEmail: (organizationId: string, email: string) =>
		request<{ email: string }>(
			`/api/organizations/${organizationId}/join-policy/emails`,
			{ method: "POST", body: JSON.stringify({ email }) },
		),
	removeJoinPolicyEmail: (organizationId: string, email: string) =>
		request<void>(
			`/api/organizations/${organizationId}/join-policy/emails/${encodeURIComponent(email)}`,
			{ method: "DELETE" },
		),
};

export const billingClient = {
	orgPoints: (organizationId: string) =>
		request<PointsSummary>(
			`/api/me/points?organization_id=${encodeURIComponent(organizationId)}`,
		),
	packs: () => request<PointPack[]>("/api/billing/packs"),
	createOrder: (packId: string, organizationId: string) =>
		request<OrderResponse>("/api/billing/orders", {
			method: "POST",
			body: JSON.stringify({
				pack_id: packId,
				organization_id: organizationId,
			}),
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
};
