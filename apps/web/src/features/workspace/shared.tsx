import type { Evaluation, JobDetail, Requirement } from "./client";

export type TabName = "results" | "criteria" | "upload";

export type EligibilityFilter = "all" | "top" | Evaluation["eligibility"];
export type OutcomeFilter = "all" | "met" | "partial" | "not_met" | "unknown";
export type StatusFilter =
	| "all"
	| "pending"
	| "processing"
	| "complete"
	| "failed";

export type Invitation = {
	token: string;
	passcode: string;
	expiresAt: string;
};

export type WindowStatus = { label: string; className: string };

export const applicationStatus = (job: JobDetail): WindowStatus => {
	if (!job.applicationOpensAt || !job.applicationClosesAt) {
		return {
			label: "no application window",
			className: "status-chip chip-muted",
		};
	}
	const now = Date.now();
	const opens = new Date(job.applicationOpensAt).getTime();
	const closes = new Date(job.applicationClosesAt).getTime();
	if (now < opens) {
		return {
			label: `opens ${new Date(opens).toLocaleDateString()}`,
			className: "status-chip chip-outline",
		};
	}
	if (now >= closes) {
		return {
			label: "applications closed",
			className: "status-chip chip-muted",
		};
	}
	return {
		label: `open until ${new Date(closes).toLocaleDateString()}`,
		className: "status-chip chip-solid",
	};
};

// datetime-local inputs need "YYYY-MM-DDTHH:mm" in local time.
export const toLocalInput = (iso: string | null) =>
	iso
		? new Date(iso).toLocaleString("sv").replace(" ", "T").slice(0, 16)
		: "";

export const draftsToRequirements = (job: JobDetail): Requirement[] =>
	job.draftRequirements.map((requirement) => ({
		...requirement,
		kind:
			requirement.assessability === "resume_evidence"
				? requirement.suggestedKind
				: "ignored",
		weight: requirement.suggestedWeight,
	}));

export const eligibilityChipClass = (
	eligibility: Evaluation["eligibility"],
): string =>
	eligibility === "eligible"
		? "status-chip chip-solid"
		: eligibility === "needs_review"
			? "status-chip chip-outline"
			: eligibility === "not_eligible"
				? "status-chip chip-soft"
				: "status-chip chip-muted";

export const outcomeChipClass = (
	outcome: Evaluation["assessments"][number]["outcome"],
): string =>
	outcome === "met"
		? "status-chip chip-solid"
		: outcome === "partial"
			? "status-chip chip-outline"
			: outcome === "not_met"
				? "status-chip chip-soft"
				: "status-chip chip-muted";

type OverlayProps = {
	onDismiss: () => void;
	labelledBy: string;
};

export const overlayBackdrop = ({ onDismiss, labelledBy }: OverlayProps) => ({
	"aria-labelledby": labelledBy,
	"aria-modal": true as const,
	className: "modal-backdrop",
	onClick: (event: React.MouseEvent<HTMLDivElement>) => {
		if (event.target === event.currentTarget) onDismiss();
	},
	onKeyDown: (event: React.KeyboardEvent<HTMLDivElement>) => {
		if (event.key === "Escape") onDismiss();
	},
	role: "dialog" as const,
});
