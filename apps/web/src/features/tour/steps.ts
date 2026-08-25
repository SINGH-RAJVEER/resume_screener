import type { TourStep } from "./types";

export const TOUR_STEPS: TourStep[] = [
	{
		act: "employer",
		body: "This is the Northwind Robotics employer organization. It has one confirmed role, six candidate submissions, and completed evaluations ready to review. Use Next to walk through it, or Escape to leave at any time.",
		id: "employer-welcome",
		title: "See how employers screen with evidence",
	},
	{
		act: "employer",
		body: "Every evaluation belongs to a job inside the organization. This role was created from a pasted description, and its requirements are already confirmed.",
		id: "employer-roles",
		prepare: (actions) => actions.closeOverlays?.(),
		target: "role-library",
		title: "Roles live in one library",
	},
	{
		act: "employer",
		body: "Draft criteria were extracted from the description first. The recruiter classified each one as required, preferred, ignored, or a hard gate, edited weights, and confirmed them into an immutable version. Nothing is scored against unconfirmed criteria.",
		id: "employer-criteria",
		prepare: (actions) => {
			actions.closeOverlays?.();
			actions.openTab?.("criteria");
		},
		target: "tab-criteria",
		title: "Recruiters confirm requirements before scoring",
	},
	{
		act: "employer",
		body: "Score, evidence coverage, and eligibility are visible per row without opening anything. Scores come only from confirmed requirements, weighted exactly as the recruiter set them.",
		id: "employer-results",
		prepare: (actions) => {
			actions.closeOverlays?.();
			actions.openTab?.("results");
		},
		target: "tab-results",
		title: "Top matches rank by explainable score",
	},
	{
		act: "employer",
		body: "Lena's resume is still being evaluated, so her row shows progress instead of pretending to have a result. Scores appear only when the work completes.",
		id: "employer-progress",
		target: "row-processing",
		title: "Processing replaces scores, honestly",
	},
	{
		act: "employer",
		body: "The default view excludes evaluations that failed a hard gate. This selector can reveal them, along with filters for score, coverage, outcome, skills, and processing state.",
		id: "employer-filter",
		prepare: (actions) => actions.showAllCandidates?.(),
		target: "eligibility-filter",
		title: "Failed gates stay reviewable through filters",
	},
	{
		act: "employer",
		body: "Tom scored 75 but is marked not eligible: his resume states he is self-taught, which contradicts the degree hard gate. The gate never adds to the score, but it decides eligibility.",
		id: "employer-gate-row",
		target: "row-not-eligible",
		title: "A failed hard gate overrides the score",
	},
	{
		act: "employer",
		body: "Every criterion shows its outcome, its share of the score, and the exact resume lines behind the judgment. Missing evidence is reported as unknown, never as failure.",
		id: "employer-evidence",
		prepare: (actions) =>
			actions.openEvidence?.("demo-evaluation-ana-reyes"),
		target: "evidence-drawer",
		title: "Open any row to audit the reasoning",
	},
	{
		act: "employer",
		body: "Exports use the exact server-side filter snapshot from when they start. Columns are selectable, reorderable, and renameable; ZIP exports bundle authorized resumes and reports.",
		id: "employer-export",
		prepare: (actions) => {
			actions.closeOverlays?.();
			actions.openExport?.();
		},
		target: "export-dialog",
		title: "Take the results with you",
	},
	{
		act: "employer",
		body: "Owners manage members, join policies, retention, and billing here. Recruiters run jobs; viewers read without exporting.",
		id: "employer-members",
		prepare: (actions) => {
			actions.closeOverlays?.();
			actions.openMembers?.();
		},
		target: "members-dialog",
		title: "Access belongs to the organization",
	},
	{
		act: "employer",
		body: "You have seen requirement confirmation, batch screening, gated eligibility, cited evidence, and exports. Next, we switch to what a candidate sees on the same platform.",
		id: "employer-outro",
		title: "That is the employer side",
	},

	{
		act: "candidate",
		body: "This account belongs to Jordan, a candidate. Employers never see this workspace, and independent evaluations stay private to Jordan unless separately submitted to a job.",
		id: "candidate-welcome",
		title: "Now see the candidate side",
	},
	{
		act: "candidate",
		body: "Upload a PDF, DOCX, or TXT resume. Adding an optional job description produces role-specific guidance; leaving it out produces a general document-quality report.",
		id: "candidate-form",
		target: "candidate-form",
		title: "A private check starts with one document",
	},
	{
		act: "candidate",
		body: "One free evaluation resets every week. Additional checks draw points from a prepaid balance, and the maximum charge is quoted before anything runs.",
		id: "candidate-points",
		target: "billing-strip",
		title: "The weekly allowance is visible up front",
	},
	{
		act: "candidate",
		body: "Completed checks stay here. Reports can be reopened or deleted at any time, which removes the documents, extracted data, and report together.",
		id: "candidate-history",
		target: "candidate-history",
		title: "History stays under your control",
	},
	{
		act: "candidate",
		body: "Seventy-two of one hundred for the target role. The report quotes the resume lines that earned the score, lists documented facts, and suggests wording changes that preserve real experience instead of inventing any.",
		id: "candidate-report",
		prepare: (actions) =>
			actions.openReport?.("demo-independent-role-report"),
		target: "report-preview",
		title: "Every score cites its evidence",
	},
	{
		act: "candidate",
		body: "Suggestions keep identity, employers, dates, and achievements untouched. A corrected resume can be downloaded directly from the report.",
		id: "candidate-download",
		target: "download-corrected",
		title: "Corrections never invent facts",
	},
	{
		act: "candidate",
		body: "Candidates submit to an employer job only through a single-use invitation link or passcode while the application window is open. That channel shows upload and receipt only, never the employer's evaluation.",
		id: "candidate-submission",
		prepare: (actions) => {
			actions.closeReport?.();
			actions.openTask?.("job-submission");
		},
		target: "submission-form",
		title: "Submitting to an employer is separate",
	},
	{
		act: "candidate",
		body: "You have seen both sides: recruiters screen with confirmed requirements and cited evidence, and candidates keep their resumes private. Create an account to try it with your own data.",
		id: "candidate-outro",
		title: "That is the whole picture",
	},
];
