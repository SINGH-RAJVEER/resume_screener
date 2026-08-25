export type TourAct = "employer" | "candidate";

export type EmployerTourActions = {
	closeOverlays: () => void;
	openTab: (tab: "results" | "criteria" | "upload") => void;
	showAllCandidates: () => void;
	openEvidence: (evaluationId: string) => void;
	openExport: () => void;
	openMembers: () => void;
};

export type CandidateTourActions = {
	openTask: (task: "private-check" | "job-submission") => void;
	openReport: (evaluationId: string) => void;
	closeReport: () => void;
};

export type TourActions = Partial<EmployerTourActions & CandidateTourActions>;

export interface TourStep {
	id: string;
	act: TourAct;
	title: string;
	body: string;
	/** Value of the data-tour attribute to spotlight. */
	target?: string;
	/** Runs when the step becomes active, before the target is awaited. */
	prepare?: (actions: TourActions) => void;
}

export const actLabel = (act: TourAct) =>
	act === "employer" ? "Employer organization" : "Candidate";
