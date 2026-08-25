import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import {
	Briefcase,
	ChevronRight,
	Copy,
	Link as LinkIcon,
	Plus,
	UploadCloud,
	X,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";
import { authClient } from "../../lib/auth-client";
import {
	type Evaluation,
	type EvaluationFilters,
	type Job,
	type JobDetail,
	type Organization,
	type Requirement,
	workspaceClient,
} from "./client";
import { CriteriaTab } from "./criteria-tab";
import { EvidenceDrawer } from "./evidence-drawer";
import { ExportDialog } from "./export-dialog";
import {
	ApplicationWindowDialog,
	CreateJobDialog,
	CreateOrganizationDialog,
} from "./job-dialogs";
import { MembersDialog } from "./members-dialog";
import { ResultsTab } from "./results-tab";
import {
	applicationStatus,
	draftsToRequirements,
	type EligibilityFilter,
	type Invitation,
	type OutcomeFilter,
	overlayBackdrop,
	type StatusFilter,
	type TabName,
} from "./shared";
import { UploadTab } from "./upload-tab";

export const Workspace = () => {
	const { data: session, isPending } = authClient.useSession();
	const [organization, setOrganization] = useState<Organization | null>(null);
	const organizationId = organization?.id ?? "";
	const [jobs, setJobs] = useState<Job[]>([]);
	const [jobSearch, setJobSearch] = useState("");
	const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
	const [activeTab, setActiveTab] = useState<TabName>("results");
	const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
	const [inspectingEvaluation, setInspectingEvaluation] =
		useState<Evaluation | null>(null);
	const [isCreateOrgOpen, setIsCreateOrgOpen] = useState(false);
	const [isCreateJobOpen, setIsCreateJobOpen] = useState(false);
	const [requirements, setRequirements] = useState<Requirement[]>([]);
	const [resumes, setResumes] = useState<File[]>([]);
	const [uploadInputKey, setUploadInputKey] = useState(0);
	const appendResumes = (files: File[]) =>
		setResumes((current) => [...current, ...files]);
	const [invitation, setInvitation] = useState<Invitation | null>(null);
	const [inviteHours, setInviteHours] = useState(168);
	const [copiedInvitation, setCopiedInvitation] = useState(false);
	const [isWindowOpen, setIsWindowOpen] = useState(false);
	const [isMembersOpen, setIsMembersOpen] = useState(false);
	const [evaluationQuery, setEvaluationQuery] = useState("");
	const [eligibilityFilter, setEligibilityFilter] =
		useState<EligibilityFilter>("top");
	const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
	const [skillFilter, setSkillFilter] = useState("");
	const [minimumScoreText, setMinimumScoreText] = useState("");
	const [isExportOpen, setIsExportOpen] = useState(false);
	const [notice, setNotice] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const reportError = useCallback((reason: unknown) => {
		setNotice(null);
		setError(reason instanceof Error ? reason.message : "Request failed");
	}, []);

	const closeOverlays = useCallback(() => {
		setIsCreateOrgOpen(false);
		setIsCreateJobOpen(false);
		setIsWindowOpen(false);
		setIsMembersOpen(false);
		setIsExportOpen(false);
		setInspectingEvaluation(null);
	}, []);

	const refreshEvaluations = useCallback(
		async (jobId: string) => {
			const filters: EvaluationFilters = {};
			if (eligibilityFilter === "top") {
				filters.eligibility = ["eligible", "needs_review", "pending"];
			} else if (eligibilityFilter !== "all") {
				filters.eligibility = [eligibilityFilter];
			}
			if (outcomeFilter !== "all") {
				filters.outcome = [outcomeFilter];
			}
			if (statusFilter !== "all") {
				filters.status = [statusFilter];
			}
			if (skillFilter.trim()) {
				filters.skill = skillFilter;
			}
			const parsedScore = Number(minimumScoreText);
			if (
				minimumScoreText.trim() !== "" &&
				Number.isFinite(parsedScore)
			) {
				filters.minimumScore = Math.min(
					100,
					Math.max(0, Math.round(parsedScore)),
				);
			}
			setEvaluations(await workspaceClient.evaluations(jobId, filters));
		},
		[
			eligibilityFilter,
			minimumScoreText,
			outcomeFilter,
			skillFilter,
			statusFilter,
		],
	);

	const openJob = useCallback(
		async (job: Job) => {
			try {
				const detail = await workspaceClient.job(job.id);
				setSelectedJob(detail);
				setInspectingEvaluation(null);
				setRequirements(
					detail.requirements.length
						? detail.requirements.map((requirement) => ({
								...requirement,
								normalizedText:
									requirement.text ??
									requirement.normalizedText,
							}))
						: draftsToRequirements(detail),
				);
				setActiveTab(detail.confirmed ? "results" : "criteria");
			} catch (reason) {
				reportError(reason);
			}
		},
		[reportError],
	);

	useEffect(() => {
		if (!session?.user) return;
		void workspaceClient
			.organizations()
			.then((records) => setOrganization(records[0] ?? null))
			.catch(reportError);
	}, [session?.user, reportError]);

	useEffect(() => {
		if (!organizationId) return;
		setInvitation(null);
		setSelectedJob(null);
		setInspectingEvaluation(null);
		void workspaceClient
			.jobs(organizationId)
			.then(async (list) => {
				setJobs(list);
				const firstJob = list[0];
				if (firstJob) await openJob(firstJob);
			})
			.catch(reportError);
	}, [organizationId, openJob, reportError]);

	useEffect(() => {
		if (!selectedJob) return;
		void refreshEvaluations(selectedJob.id).catch(reportError);
	}, [selectedJob, refreshEvaluations, reportError]);

	useEffect(() => {
		if (selectedJob?.draftStatus !== "processing") return;
		const jobId = selectedJob.id;
		const interval = window.setInterval(() => {
			void workspaceClient
				.job(jobId)
				.then((detail) => {
					setSelectedJob((current) =>
						current?.id === jobId ? detail : current,
					);
					if (detail.draftStatus !== "processing") {
						setRequirements((current) =>
							current.length
								? current
								: draftsToRequirements(detail),
						);
					}
				})
				.catch(() => {});
		}, 1_500);
		return () => window.clearInterval(interval);
	}, [selectedJob]);

	const hasPendingEvaluations = evaluations.some(
		(evaluation) => evaluation.status !== "complete",
	);

	useEffect(() => {
		if (!selectedJob || !hasPendingEvaluations) return;
		const jobId = selectedJob.id;
		const interval = window.setInterval(() => {
			void refreshEvaluations(jobId).catch(() => {});
		}, 3_000);
		return () => window.clearInterval(interval);
	}, [selectedJob, hasPendingEvaluations, refreshEvaluations]);

	const overlayOpen =
		isCreateOrgOpen ||
		isCreateJobOpen ||
		isWindowOpen ||
		isMembersOpen ||
		inspectingEvaluation !== null;

	useEffect(() => {
		if (!overlayOpen) return;
		const onKeyDown = (event: KeyboardEvent) => {
			if (event.key === "Escape") closeOverlays();
		};
		window.addEventListener("keydown", onKeyDown);
		return () => window.removeEventListener("keydown", onKeyDown);
	}, [overlayOpen, closeOverlays]);

	if (isPending) {
		return (
			<main className="workspace-page">
				<p className="empty-state loading-inline" role="status">
					<ThinkingOrb aria-hidden size={20} state="solving" />
					Loading workspace...
				</p>
			</main>
		);
	}

	if (!session?.user) {
		return (
			<main className="workspace-page">
				<section className="auth-page">
					<div className="auth-panel">
						<h1 style={{ fontSize: "1.5rem", fontWeight: 400 }}>
							Sign in to access the employer workspace
						</h1>
						<Button asChild className="w-full">
							<a href="/sign-in">Sign in</a>
						</Button>
					</div>
				</section>
			</main>
		);
	}

	const confirm = async () => {
		if (!selectedJob) return;
		try {
			await workspaceClient.confirmRequirements(
				selectedJob.id,
				requirements,
			);
			const updated = await workspaceClient.job(selectedJob.id);
			setSelectedJob(updated);
			setNotice(
				"Requirements confirmed into a new immutable version. Submissions are scored against it.",
			);
			setActiveTab("results");
		} catch (reason) {
			reportError(reason);
		}
	};

	const upload = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!selectedJob || resumes.length === 0) return;
		try {
			const archives = resumes.filter((resume) =>
				resume.name.toLowerCase().endsWith(".zip"),
			);
			const documents = resumes.filter(
				(resume) => !resume.name.toLowerCase().endsWith(".zip"),
			);
			const outcomes = await Promise.allSettled([
				...archives.map((archive) =>
					workspaceClient.uploadResumeBatch(selectedJob.id, archive),
				),
				...(documents.length > 0
					? [
							workspaceClient.uploadResumeFiles(
								selectedJob.id,
								documents,
							),
						]
					: []),
			]);
			const accepted: Array<{ name: string }> = [];
			const rejected: Array<{ name: string; reason: string }> = [];
			for (const outcome of outcomes) {
				if (outcome.status === "fulfilled") {
					accepted.push(...outcome.value.accepted);
					rejected.push(...outcome.value.rejected);
				} else {
					rejected.push({
						name: "Upload",
						reason:
							outcome.reason instanceof Error
								? outcome.reason.message
								: "Upload failed",
					});
				}
			}
			setResumes([]);
			setUploadInputKey((current) => current + 1);
			await refreshEvaluations(selectedJob.id);
			setActiveTab("results");
			setNotice(
				`${accepted.length} resume${accepted.length === 1 ? "" : "s"} queued.`,
			);
			if (rejected.length) {
				setError(
					rejected
						.map(
							(rejection) =>
								`${rejection.name}: ${rejection.reason}`,
						)
						.join(" "),
				);
			}
		} catch (reason) {
			reportError(reason);
		}
	};

	const handleCreateInvitation = async () => {
		if (!selectedJob) return;
		try {
			const created = await workspaceClient.createInvitation(
				selectedJob.id,
				inviteHours,
			);
			setInvitation({
				token: created.token,
				passcode: created.passcode,
				expiresAt: created.expiresAt,
			});
			setNotice(
				"Single-use invitation created. Share the link or the passcode.",
			);
		} catch (reason) {
			reportError(reason);
		}
	};

	const copyInvitationLink = () => {
		if (!invitation) return;
		const link = `${window.location.origin}/apply/${invitation.token}`;
		void navigator.clipboard.writeText(link);
		setCopiedInvitation(true);
		setTimeout(() => setCopiedInvitation(false), 2_000);
	};

	const visibleEvaluations = evaluations.filter((evaluation) => {
		const query = evaluationQuery.trim().toLowerCase();
		if (!query) return true;
		return `${evaluation.candidateName ?? ""} ${evaluation.candidateEmail ?? ""}`
			.toLowerCase()
			.includes(query);
	});

	const filteredJobs = jobs.filter((job) =>
		job.title.toLowerCase().includes(jobSearch.toLowerCase()),
	);
	const startCreateJob = () => {
		if (organizationId) setIsCreateJobOpen(true);
		else setIsCreateOrgOpen(true);
	};

	return (
		<div className="workspace-page">
			<header className="workspace-header">
				<div className="workspace-header-left">
					<a href="/" className="brand-mark">
						<img src="/icon.webp" alt="SkillSignal" />
					</a>
					{organization && (
						<div className="workspace-org">
							<span>Organization</span>
							<strong>{organization.name}</strong>
						</div>
					)}
				</div>
				<div className="workspace-header-right">
					<Button
						disabled={!organizationId}
						onClick={() => setIsMembersOpen(true)}
						size="sm"
						variant="outline"
					>
						Members
					</Button>
					<span>{session.user.name || session.user.email}</span>
					<Button
						onClick={() => authClient.signOut()}
						size="sm"
						variant="outline"
					>
						Sign out
					</Button>
				</div>
			</header>

			{notice && (
				<div className="workspace-banner">
					<span>{notice}</span>
					<button
						aria-label="Dismiss notice"
						className="icon-button"
						onClick={() => setNotice(null)}
						type="button"
					>
						<X />
					</button>
				</div>
			)}
			{error && (
				<div className="workspace-banner banner-error">
					<span>{error}</span>
					<button
						aria-label="Dismiss error"
						className="icon-button"
						onClick={() => setError(null)}
						type="button"
					>
						<X />
					</button>
				</div>
			)}

			<div className="workspace-layout">
				<aside className="workspace-aside">
					<div className="workspace-aside-head">
						<h2>Roles</h2>
						<Button onClick={startCreateJob} size="sm">
							<Plus />
							New role
						</Button>
					</div>
					<div>
						<Input
							aria-label="Search roles"
							onChange={(event) =>
								setJobSearch(event.target.value)
							}
							placeholder="Search roles..."
							value={jobSearch}
						/>
					</div>
					<nav aria-label="Roles" className="role-list">
						{filteredJobs.map((job) => (
							<button
								key={job.id}
								className={`role-item${
									selectedJob?.id === job.id ? " active" : ""
								}`}
								onClick={() => void openJob(job)}
								type="button"
							>
								<span>
									<span className="role-item-name">
										{job.title}
									</span>
									<span className="role-item-meta">
										{job.confirmed
											? "confirmed"
											: "draft criteria"}
									</span>
								</span>
								<ChevronRight aria-hidden />
							</button>
						))}
						{filteredJobs.length === 0 && (
							<p className="muted-copy">
								No roles yet. Create one to start screening.
							</p>
						)}
					</nav>
				</aside>

				<main className="workspace-main">
					{selectedJob ? (
						<div className="workspace-stage">
							<div className="job-head">
								<div>
									<div className="job-title-row">
										<h1>{selectedJob.title}</h1>
										<span
											className={
												selectedJob.confirmed
													? "status-chip chip-solid"
													: "status-chip chip-outline"
											}
										>
											{selectedJob.confirmed
												? "requirements confirmed"
												: "needs confirmation"}
										</span>
										<span
											className={
												applicationStatus(selectedJob)
													.className
											}
										>
											{
												applicationStatus(selectedJob)
													.label
											}
										</span>
									</div>
									<p className="job-meta">
										{organization?.name} ·{" "}
										{evaluations.length} submission
										{evaluations.length === 1 ? "" : "s"}{" "}
										evaluated
									</p>
								</div>
								<div className="job-actions">
									<Button
										onClick={() => setIsWindowOpen(true)}
										size="sm"
										variant="outline"
									>
										Application window
									</Button>
									<select
										aria-label="Invitation validity"
										className="workspace-filter-select"
										onChange={(event) =>
											setInviteHours(
												Number(event.target.value),
											)
										}
										value={inviteHours}
									>
										<option value={24}>
											Invite valid 24 h
										</option>
										<option value={168}>
											Invite valid 7 days
										</option>
										<option value={720}>
											Invite valid 30 days
										</option>
									</select>
									<Button
										onClick={() =>
											void handleCreateInvitation()
										}
										size="sm"
										variant="outline"
									>
										<LinkIcon />
										Invite candidate
									</Button>
									<Button
										onClick={() => setActiveTab("upload")}
										size="sm"
									>
										<UploadCloud />
										Queue resumes
									</Button>
								</div>
							</div>

							{invitation && (
								<div className="invitation-strip">
									<div className="invitation-facts">
										<span>
											Link{" "}
											<code>{`${window.location.origin}/apply/${invitation.token}`}</code>
										</span>
										<span>
											Passcode{" "}
											<code className="passcode">
												{invitation.passcode}
											</code>
										</span>
										<span className="muted-copy">
											expires{" "}
											{new Date(
												invitation.expiresAt,
											).toLocaleString()}
										</span>
									</div>
									<Button
										onClick={copyInvitationLink}
										size="sm"
										variant="outline"
									>
										<Copy />
										{copiedInvitation
											? "Copied"
											: "Copy link"}
									</Button>
								</div>
							)}

							<nav aria-label="Job sections" className="job-tabs">
								<button
									className={`job-tab${
										activeTab === "results" ? " active" : ""
									}`}
									onClick={() => setActiveTab("results")}
									type="button"
								>
									Top matches ({evaluations.length})
								</button>
								<button
									className={`job-tab${
										activeTab === "criteria"
											? " active"
											: ""
									}`}
									onClick={() => setActiveTab("criteria")}
									type="button"
								>
									Criteria ({requirements.length})
								</button>
								<button
									className={`job-tab${
										activeTab === "upload" ? " active" : ""
									}`}
									onClick={() => setActiveTab("upload")}
									type="button"
								>
									Upload
								</button>
							</nav>

							{activeTab === "results" && (
								<ResultsTab
									evaluations={evaluations}
									eligibilityFilter={eligibilityFilter}
									exportCsv={() => setIsExportOpen(true)}
									minimumScoreText={minimumScoreText}
									onInspect={setInspectingEvaluation}
									onQueue={() => setActiveTab("upload")}
									visibleEvaluations={visibleEvaluations}
									setEligibilityFilter={setEligibilityFilter}
									setEvaluationQuery={setEvaluationQuery}
									setMinimumScoreText={setMinimumScoreText}
									setOutcomeFilter={setOutcomeFilter}
									setSkillFilter={setSkillFilter}
									setStatusFilter={setStatusFilter}
									evaluationQuery={evaluationQuery}
									outcomeFilter={outcomeFilter}
									skillFilter={skillFilter}
									statusFilter={statusFilter}
								/>
							)}

							{activeTab === "criteria" && (
								<CriteriaTab
									canConfirm={
										requirements.length > 0 &&
										selectedJob.draftStatus !== "processing"
									}
									confirmed={selectedJob.confirmed}
									draftError={selectedJob.draftError}
									draftDegraded={selectedJob.draftDegraded}
									draftStatus={selectedJob.draftStatus}
									draftWarnings={selectedJob.draftWarnings}
									onAdd={() =>
										setRequirements((current) => [
											...current,
											{
												stableId: `custom_${Date.now()}`,
												normalizedText: "",
												kind: "required",
												weight: 2,
												category: "other",
												assessability:
													"resume_evidence",
											},
										])
									}
									onConfirm={() => void confirm()}
									onChange={(index, patch) =>
										setRequirements((current) =>
											current.map((item, itemIndex) =>
												itemIndex === index
													? { ...item, ...patch }
													: item,
											),
										)
									}
									requirements={requirements}
								/>
							)}

							{activeTab === "upload" && (
								<UploadTab
									confirmed={selectedJob.confirmed}
									onConfirmCriteria={() =>
										setActiveTab("criteria")
									}
									onSubmit={(event) => void upload(event)}
									resumes={resumes}
									appendResumes={appendResumes}
									uploadInputKey={uploadInputKey}
								/>
							)}
						</div>
					) : (
						<div className="empty-state">
							<Briefcase aria-hidden />
							<h3>
								{organizationId
									? "Select a role"
									: "Create your organization"}
							</h3>
							<p>
								{organizationId
									? "Choose a role from the sidebar, or create a new one."
									: "An employer organization owns your roles, submissions, and evaluations."}
							</p>
							<Button onClick={startCreateJob} size="sm">
								<Plus />
								{organizationId
									? "New role"
									: "Create organization"}
							</Button>
						</div>
					)}
				</main>
			</div>

			{isCreateOrgOpen && (
				<CreateOrganizationDialog
					onDismiss={() => setIsCreateOrgOpen(false)}
					onError={reportError}
					onCreated={(created) => {
						closeOverlays();
						setOrganization(created);
						setNotice("Employer organization created.");
					}}
				/>
			)}

			{isCreateJobOpen && (
				<CreateJobDialog
					organizationId={organizationId}
					onDismiss={() => setIsCreateJobOpen(false)}
					onError={reportError}
					onCreated={(detail) => {
						closeOverlays();
						setSelectedJob(detail);
						setRequirements(draftsToRequirements(detail));
						setActiveTab("criteria");
						void workspaceClient
							.jobs(organizationId)
							.then(setJobs)
							.catch(reportError);
						setNotice(
							"Role created. Requirement extraction is running before recruiter review.",
						);
					}}
				/>
			)}

			{isWindowOpen && selectedJob && (
				<ApplicationWindowDialog
					job={selectedJob}
					onDismiss={() => setIsWindowOpen(false)}
					onError={reportError}
					onSaved={(detail) => {
						setIsWindowOpen(false);
						setSelectedJob(detail);
						setNotice("Application window updated.");
					}}
				/>
			)}

			{isMembersOpen && organization && (
				<MembersDialog
					organization={organization}
					onDismiss={() => setIsMembersOpen(false)}
					onNotice={setNotice}
					onError={reportError}
				/>
			)}

			{isExportOpen && selectedJob && (
				<ExportDialog
					jobId={selectedJob.id}
					onDismiss={() => setIsExportOpen(false)}
					onError={reportError}
				/>
			)}

			{inspectingEvaluation && (
				<div
					{...overlayBackdrop({
						labelledBy: "evidence-title",
						onDismiss: () => setInspectingEvaluation(null),
					})}
					className="drawer-backdrop"
				>
					<EvidenceDrawer
						evaluation={inspectingEvaluation}
						onClose={() => setInspectingEvaluation(null)}
					/>
				</div>
			)}
		</div>
	);
};
