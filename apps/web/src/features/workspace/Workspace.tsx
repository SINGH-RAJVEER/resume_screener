import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { Textarea } from "@resume-screener/ui/components/textarea";
import {
	Briefcase,
	CheckCircle2,
	ChevronRight,
	Copy,
	Download,
	FileText,
	Link as LinkIcon,
	LoaderCircle,
	Plus,
	UploadCloud,
	X,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { authClient } from "../../lib/auth-client";
import {
	type Evaluation,
	type EvaluationFilters,
	type Job,
	type JobDetail,
	type Member,
	type Organization,
	type Requirement,
	workspaceClient,
} from "./client";

type TabName = "results" | "criteria" | "upload";

type EligibilityFilter = "all" | Evaluation["eligibility"];

type Invitation = {
	token: string;
	passcode: string;
	expiresAt: string;
};

type WindowStatus = { label: string; className: string };

const applicationStatus = (job: JobDetail): WindowStatus => {
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
const toLocalInput = (iso: string | null) =>
	iso
		? new Date(iso).toLocaleString("sv").replace(" ", "T").slice(0, 16)
		: "";

const draftsToRequirements = (job: JobDetail): Requirement[] =>
	job.draftRequirements.map((requirement) => ({
		...requirement,
		kind: "required",
		weight: 2,
	}));

const eligibilityChipClass = (
	eligibility: Evaluation["eligibility"],
): string =>
	eligibility === "eligible"
		? "status-chip chip-solid"
		: eligibility === "needs_review"
			? "status-chip chip-outline"
			: eligibility === "not_eligible"
				? "status-chip chip-soft"
				: "status-chip chip-muted";

const outcomeChipClass = (
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

const overlayBackdrop = ({ onDismiss, labelledBy }: OverlayProps) => ({
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

export const Workspace = () => {
	const { data: session, isPending } = authClient.useSession();
	const [organizations, setOrganizations] = useState<Organization[]>([]);
	const [organizationId, setOrganizationId] = useState("");
	const [jobs, setJobs] = useState<Job[]>([]);
	const [jobSearch, setJobSearch] = useState("");
	const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
	const [activeTab, setActiveTab] = useState<TabName>("results");
	const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
	const [inspectingEvaluation, setInspectingEvaluation] =
		useState<Evaluation | null>(null);
	const [isCreateOrgOpen, setIsCreateOrgOpen] = useState(false);
	const [isCreateJobOpen, setIsCreateJobOpen] = useState(false);
	const [organizationName, setOrganizationName] = useState("");
	const [jobTitle, setJobTitle] = useState("");
	const [description, setDescription] = useState("");
	const [requirements, setRequirements] = useState<Requirement[]>([]);
	const [resumes, setResumes] = useState<File[]>([]);
	const [uploadInputKey, setUploadInputKey] = useState(0);
	const [invitation, setInvitation] = useState<Invitation | null>(null);
	const [inviteHours, setInviteHours] = useState(168);
	const [copiedInvitation, setCopiedInvitation] = useState(false);
	const [isWindowOpen, setIsWindowOpen] = useState(false);
	const [windowOpens, setWindowOpens] = useState("");
	const [windowCloses, setWindowCloses] = useState("");
	const [isMembersOpen, setIsMembersOpen] = useState(false);
	const [members, setMembers] = useState<Member[]>([]);
	const [memberEmail, setMemberEmail] = useState("");
	const [memberRole, setMemberRole] =
		useState<Pick<Member, "role">["role"]>("recruiter");
	const [evaluationQuery, setEvaluationQuery] = useState("");
	const [eligibilityFilter, setEligibilityFilter] =
		useState<EligibilityFilter>("all");
	const [minimumScoreText, setMinimumScoreText] = useState("");
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
		setInspectingEvaluation(null);
	}, []);

	const refreshEvaluations = useCallback(
		async (jobId: string) => {
			const filters: EvaluationFilters = {};
			if (eligibilityFilter !== "all") {
				filters.eligibility = [eligibilityFilter];
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
		[eligibilityFilter, minimumScoreText],
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
			.then((records) => {
				setOrganizations(records);
				setOrganizationId(records[0]?.id ?? "");
			})
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
				<p className="empty-state">Loading workspace...</p>
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

	const currentOrg = organizations.find((org) => org.id === organizationId);

	const createOrganization = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!organizationName.trim()) return;
		try {
			const organization =
				await workspaceClient.createOrganization(organizationName);
			setOrganizationName("");
			setIsCreateOrgOpen(false);
			setOrganizations((current) => [...current, organization]);
			setOrganizationId(organization.id);
			setNotice("Employer organization created.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const createJob = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!jobTitle.trim() || !description.trim() || !organizationId) return;
		try {
			const job = await workspaceClient.createJob(
				organizationId,
				jobTitle,
				description,
			);
			const detail = await workspaceClient.job(job.id);
			setSelectedJob(detail);
			setRequirements(draftsToRequirements(detail));
			setJobTitle("");
			setDescription("");
			setIsCreateJobOpen(false);
			setActiveTab("criteria");
			setJobs(await workspaceClient.jobs(organizationId));
			setNotice(
				"Role created with draft criteria. Confirm them to enable resume evaluations.",
			);
		} catch (reason) {
			reportError(reason);
		}
	};

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
			const hasArchive = resumes.some((resume) =>
				resume.name.toLowerCase().endsWith(".zip"),
			);
			if (hasArchive && resumes.length !== 1) {
				setError(
					"Upload one ZIP archive, or one or more resume documents.",
				);
				return;
			}
			const [archive] = resumes;
			if (!archive) return;
			const result = hasArchive
				? await workspaceClient.uploadResumeBatch(
						selectedJob.id,
						archive,
					)
				: await workspaceClient.uploadResumes(selectedJob.id, resumes);
			setResumes([]);
			setUploadInputKey((current) => current + 1);
			await refreshEvaluations(selectedJob.id);
			setActiveTab("results");
			setNotice(
				`${result.accepted.length} resume${result.accepted.length === 1 ? "" : "s"} queued.`,
			);
			if (result.rejected.length) {
				setError(
					result.rejected
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

	const saveApplicationWindow = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!selectedJob || !windowOpens || !windowCloses) return;
		try {
			await workspaceClient.setApplicationWindow(
				selectedJob.id,
				new Date(windowOpens).toISOString(),
				new Date(windowCloses).toISOString(),
			);
			setSelectedJob(await workspaceClient.job(selectedJob.id));
			setIsWindowOpen(false);
			setNotice("Application window updated.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const openMembersModal = async () => {
		setIsMembersOpen(true);
		try {
			setMembers(await workspaceClient.members(organizationId));
		} catch (reason) {
			reportError(reason);
		}
	};

	const addMember = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!memberEmail.trim()) return;
		try {
			const added = await workspaceClient.addMember(
				organizationId,
				memberEmail,
				memberRole,
			);
			setMemberEmail("");
			setMemberRole("recruiter");
			setMembers(await workspaceClient.members(organizationId));
			setNotice(`Member added as ${added.role}.`);
		} catch (reason) {
			reportError(reason);
		}
	};

	const removeMember = async (userId: string) => {
		try {
			await workspaceClient.removeMember(organizationId, userId);
			setMembers(await workspaceClient.members(organizationId));
			setNotice("Member removed.");
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

	const exportCsv = async () => {
		if (!selectedJob) return;
		try {
			await workspaceClient.exportEvaluationsCsv(selectedJob.id);
		} catch (reason) {
			reportError(reason);
		}
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
						<span>rs</span>
						<span className="brand-name">resume screener</span>
					</a>
					<div className="workspace-org">
						<span>Organization</span>
						<select
							aria-label="Employer organization"
							onChange={(event) =>
								setOrganizationId(event.target.value)
							}
							value={organizationId}
						>
							{organizations.map((org) => (
								<option key={org.id} value={org.id}>
									{org.name} ({org.role})
								</option>
							))}
						</select>
						<Button
							onClick={() => setIsCreateOrgOpen(true)}
							size="sm"
							variant="outline"
						>
							<Plus />
							New
						</Button>
					</div>
				</div>
				<div className="workspace-header-right">
					<Button
						disabled={!organizationId}
						onClick={() => void openMembersModal()}
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
										{currentOrg?.name} ·{" "}
										{evaluations.length} submission
										{evaluations.length === 1 ? "" : "s"}{" "}
										evaluated
									</p>
								</div>
								<div className="job-actions">
									<Button
										onClick={() => {
											setWindowOpens(
												toLocalInput(
													selectedJob.applicationOpensAt,
												),
											);
											setWindowCloses(
												toLocalInput(
													selectedJob.applicationClosesAt,
												),
											);
											setIsWindowOpen(true);
										}}
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
									exportCsv={() => void exportCsv()}
									minimumScoreText={minimumScoreText}
									onInspect={setInspectingEvaluation}
									onQueue={() => setActiveTab("upload")}
									visibleEvaluations={visibleEvaluations}
									{...{
										setEligibilityFilter,
										setEvaluationQuery,
										setMinimumScoreText,
									}}
									evaluationQuery={evaluationQuery}
								/>
							)}

							{activeTab === "criteria" && (
								<CriteriaTab
									canConfirm={requirements.length > 0}
									confirmed={selectedJob.confirmed}
									onAdd={() =>
										setRequirements((current) => [
											...current,
											{
												stableId: `custom_${Date.now()}`,
												normalizedText: "",
												kind: "required",
												weight: 2,
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
									setResumes={setResumes}
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
				<div
					{...overlayBackdrop({
						labelledBy: "create-org-title",
						onDismiss: () => setIsCreateOrgOpen(false),
					})}
				>
					<form className="modal-panel" onSubmit={createOrganization}>
						<h3 id="create-org-title">Create organization</h3>
						<div className="form-field">
							<Label htmlFor="org-name">Organization name</Label>
							<Input
								id="org-name"
								onChange={(event) =>
									setOrganizationName(event.target.value)
								}
								placeholder="Acme Corp"
								required
								value={organizationName}
							/>
						</div>
						<div className="modal-actions">
							<Button
								onClick={() => setIsCreateOrgOpen(false)}
								size="sm"
								variant="outline"
								type="button"
							>
								Cancel
							</Button>
							<Button size="sm" type="submit">
								Create
							</Button>
						</div>
					</form>
				</div>
			)}

			{isCreateJobOpen && (
				<div
					{...overlayBackdrop({
						labelledBy: "create-job-title",
						onDismiss: () => setIsCreateJobOpen(false),
					})}
				>
					<form className="modal-panel" onSubmit={createJob}>
						<h3 id="create-job-title">Create role</h3>
						<div className="form-field">
							<Label htmlFor="create-job-title">Role title</Label>
							<Input
								id="create-job-title"
								onChange={(event) =>
									setJobTitle(event.target.value)
								}
								placeholder="Senior Backend Engineer"
								required
								value={jobTitle}
							/>
						</div>
						<div className="form-field">
							<Label htmlFor="create-job-description">
								Job description
							</Label>
							<Textarea
								id="create-job-description"
								onChange={(event) =>
									setDescription(event.target.value)
								}
								placeholder="Paste the full description. Draft criteria are extracted automatically."
								required
								value={description}
							/>
						</div>
						<div className="modal-actions">
							<Button
								onClick={() => setIsCreateJobOpen(false)}
								size="sm"
								variant="outline"
								type="button"
							>
								Cancel
							</Button>
							<Button size="sm" type="submit">
								Create role
							</Button>
						</div>
					</form>
				</div>
			)}

			{isWindowOpen && (
				<div
					{...overlayBackdrop({
						labelledBy: "window-title",
						onDismiss: () => setIsWindowOpen(false),
					})}
				>
					<form
						className="modal-panel"
						onSubmit={saveApplicationWindow}
					>
						<h3 id="window-title">Application window</h3>
						<p className="muted-copy">
							Candidates can submit resumes through invitations
							only while the window is open.
						</p>
						<div className="form-field">
							<Label htmlFor="window-opens">Opens at</Label>
							<Input
								id="window-opens"
								onChange={(event) =>
									setWindowOpens(event.target.value)
								}
								required
								type="datetime-local"
								value={windowOpens}
							/>
						</div>
						<div className="form-field">
							<Label htmlFor="window-closes">Closes at</Label>
							<Input
								id="window-closes"
								onChange={(event) =>
									setWindowCloses(event.target.value)
								}
								required
								type="datetime-local"
								value={windowCloses}
							/>
						</div>
						<div className="modal-actions">
							<Button
								onClick={() => setIsWindowOpen(false)}
								size="sm"
								variant="outline"
								type="button"
							>
								Cancel
							</Button>
							<Button size="sm" type="submit">
								Save window
							</Button>
						</div>
					</form>
				</div>
			)}

			{isMembersOpen && (
				<div
					{...overlayBackdrop({
						labelledBy: "members-title",
						onDismiss: () => setIsMembersOpen(false),
					})}
				>
					<div className="modal-panel">
						<div className="modal-head-row">
							<h3 id="members-title">
								Members · {currentOrg?.name}
							</h3>
							<button
								aria-label="Close members"
								className="icon-button"
								onClick={() => setIsMembersOpen(false)}
								type="button"
							>
								<X />
							</button>
						</div>
						<div className="member-list">
							{members.map((member) => (
								<div className="member-row" key={member.userId}>
									<span>
										<span style={{ fontWeight: 600 }}>
											{member.name}
										</span>
										<span className="candidate-email">
											{member.email}
										</span>
									</span>
									<span className="member-side">
										<span className="status-chip chip-muted">
											{member.role}
										</span>
										{currentOrg?.role === "owner" &&
											member.role !== "owner" && (
												<Button
													onClick={() =>
														void removeMember(
															member.userId,
														)
													}
													size="sm"
													variant="outline"
												>
													Remove
												</Button>
											)}
									</span>
								</div>
							))}
							{members.length === 0 && (
								<p className="muted-copy">Loading members...</p>
							)}
						</div>
						{currentOrg?.role === "owner" && (
							<form className="member-form" onSubmit={addMember}>
								<Input
									aria-label="Member email"
									onChange={(event) =>
										setMemberEmail(event.target.value)
									}
									placeholder="colleague@company.com"
									required
									type="email"
									value={memberEmail}
								/>
								<select
									aria-label="Member role"
									className="workspace-filter-select"
									onChange={(event) =>
										setMemberRole(
											event.target
												.value as Member["role"],
										)
									}
									value={memberRole}
								>
									<option value="recruiter">Recruiter</option>
									<option value="viewer">Viewer</option>
								</select>
								<Button size="sm" type="submit">
									<Plus />
									Add member
								</Button>
							</form>
						)}
						{currentOrg?.role !== "owner" && (
							<p className="muted-copy">
								Only owners can add or remove members.
							</p>
						)}
					</div>
				</div>
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

type ResultsTabProps = {
	evaluations: Evaluation[];
	visibleEvaluations: Evaluation[];
	evaluationQuery: string;
	eligibilityFilter: EligibilityFilter;
	minimumScoreText: string;
	setEvaluationQuery: (value: string) => void;
	setEligibilityFilter: (value: EligibilityFilter) => void;
	setMinimumScoreText: (value: string) => void;
	exportCsv: () => void;
	onQueue: () => void;
	onInspect: (evaluation: Evaluation) => void;
};

const ResultsTab = ({
	evaluations,
	visibleEvaluations,
	evaluationQuery,
	eligibilityFilter,
	minimumScoreText,
	setEvaluationQuery,
	setEligibilityFilter,
	setMinimumScoreText,
	exportCsv,
	onQueue,
	onInspect,
}: ResultsTabProps) => {
	const eligibleCount = evaluations.filter(
		(evaluation) => evaluation.eligibility === "eligible",
	).length;
	const reviewCount = evaluations.filter(
		(evaluation) => evaluation.eligibility === "needs_review",
	).length;
	const topScore = evaluations.find(
		(evaluation) => evaluation.score !== null,
	)?.score;

	return (
		<div className="workspace-stage-gap">
			<div className="stat-strip">
				<div className="stat">
					<span>Evaluated</span>
					<p>{evaluations.length}</p>
				</div>
				<div className="stat">
					<span>Top score</span>
					<p>{topScore ?? "—"}</p>
				</div>
				<div className="stat">
					<span>Eligible</span>
					<p>{eligibleCount}</p>
				</div>
				<div className="stat">
					<span>Needs review</span>
					<p>{reviewCount}</p>
				</div>
			</div>

			<div className="filter-bar">
				<div className="filter-group">
					<Input
						aria-label="Search candidates"
						onChange={(event) =>
							setEvaluationQuery(event.target.value)
						}
						placeholder="Search name or email..."
						value={evaluationQuery}
					/>
					<select
						aria-label="Filter by eligibility"
						className="workspace-filter-select"
						onChange={(event) =>
							setEligibilityFilter(
								event.target.value as EligibilityFilter,
							)
						}
						value={eligibilityFilter}
					>
						<option value="all">All outcomes</option>
						<option value="eligible">Eligible</option>
						<option value="needs_review">Needs review</option>
						<option value="not_eligible">Not eligible</option>
					</select>
					<label className="filter-minimum">
						Min score
						<input
							aria-label="Minimum score"
							max={100}
							min={0}
							onChange={(event) =>
								setMinimumScoreText(event.target.value)
							}
							placeholder="0"
							type="number"
							value={minimumScoreText}
						/>
					</label>
				</div>
				<Button onClick={exportCsv} size="sm" variant="outline">
					<Download />
					Export CSV
				</Button>
			</div>

			<div className="results-table">
				<table>
					<thead>
						<tr>
							<th scope="col">Candidate</th>
							<th scope="col">Score</th>
							<th scope="col">Eligibility</th>
							<th scope="col">Evidence coverage</th>
							<th scope="col">
								<span className="visually-hidden">Actions</span>
							</th>
						</tr>
					</thead>
					<tbody>
						{visibleEvaluations.map((evaluation) => (
							<tr key={evaluation.id}>
								<td>
									<span style={{ fontWeight: 600 }}>
										{evaluation.candidateName ??
											"Candidate"}
									</span>
									{evaluation.candidateEmail && (
										<span className="candidate-email">
											{evaluation.candidateEmail}
										</span>
									)}
								</td>
								<td>
									{evaluation.score !== null ? (
										<span className="score-cell">
											{evaluation.score}
											<span className="score-denominator">
												/100
											</span>
										</span>
									) : evaluation.status === "complete" ? (
										<span className="muted-copy">—</span>
									) : (
										<span className="pending-cell">
											<LoaderCircle
												aria-hidden
												className="spin"
											/>
											Queued
										</span>
									)}
								</td>
								<td>
									<span
										className={eligibilityChipClass(
											evaluation.eligibility,
										)}
									>
										{evaluation.eligibility.replace(
											/_/g,
											" ",
										)}
									</span>
								</td>
								<td>
									{evaluation.coverage !== null ? (
										<span className="coverage-cell">
											<span
												aria-hidden
												className="coverage-meter"
											>
												<span
													className="coverage-meter-fill"
													style={{
														width: `${Math.min(100, Math.max(0, evaluation.coverage))}%`,
													}}
												/>
											</span>
											{evaluation.coverage}%
										</span>
									) : (
										"—"
									)}
								</td>
								<td className="cell-action">
									<Button
										onClick={() => onInspect(evaluation)}
										size="sm"
										variant="outline"
									>
										Inspect
									</Button>
								</td>
							</tr>
						))}
						{visibleEvaluations.length === 0 && (
							<tr>
								<td colSpan={5}>
									{evaluations.length === 0 ? (
										<div className="empty-state">
											<FileText aria-hidden />
											<h3>No resumes evaluated yet</h3>
											<p>
												Upload resumes or invite
												candidates once criteria are
												confirmed.
											</p>
											<Button onClick={onQueue} size="sm">
												<UploadCloud />
												Queue resumes
											</Button>
										</div>
									) : (
										<p className="empty-state">
											No evaluations match the current
											filters.
										</p>
									)}
								</td>
							</tr>
						)}
					</tbody>
				</table>
			</div>
		</div>
	);
};

type CriteriaTabProps = {
	requirements: Requirement[];
	confirmed: boolean;
	canConfirm: boolean;
	onChange: (
		index: number,
		patch: Partial<Pick<Requirement, "normalizedText" | "kind" | "weight">>,
	) => void;
	onAdd: () => void;
	onConfirm: () => void;
};

const CriteriaTab = ({
	requirements,
	confirmed,
	canConfirm,
	onChange,
	onAdd,
	onConfirm,
}: CriteriaTabProps) => (
	<div className="workspace-stage-gap">
		<p className="criterion-note">
			Draft criteria are extracted from the job description. Classify each
			as required, preferred, ignored, or a hard gate before confirming.
			Confirming creates an immutable version that all scoring uses.
		</p>
		<div className="criterion-list">
			{requirements.map((requirement, index) => (
				<div className="criterion-row" key={requirement.stableId}>
					<span className="criterion-index">
						{(index + 1).toString().padStart(2, "0")}
					</span>
					<Input
						aria-label={`Requirement ${index + 1} statement`}
						className="criterion-text"
						onChange={(event) =>
							onChange(index, {
								normalizedText: event.target.value,
							})
						}
						placeholder="Requirement statement..."
						value={requirement.normalizedText ?? ""}
					/>
					<div className="criterion-kind">
						<select
							aria-label={`Requirement ${index + 1} kind`}
							onChange={(event) =>
								onChange(index, {
									kind: event.target
										.value as Requirement["kind"],
								})
							}
							value={requirement.kind}
						>
							<option value="required">Required</option>
							<option value="preferred">Preferred</option>
							<option value="hard_gate">Hard gate</option>
							<option value="ignored">Ignored</option>
						</select>
						<Input
							aria-label={`Requirement ${index + 1} weight`}
							className="weight-input"
							max={10}
							min={1}
							onChange={(event) =>
								onChange(index, {
									weight: Number(event.target.value),
								})
							}
							title="Weight (1 to 10)"
							type="number"
							value={requirement.weight}
						/>
					</div>
				</div>
			))}
		</div>
		<div className="criteria-actions">
			<Button onClick={onAdd} size="sm" variant="outline">
				<Plus />
				Add criterion
			</Button>
			<Button disabled={!canConfirm} onClick={onConfirm} size="sm">
				<CheckCircle2 />
				{confirmed ? "Confirm new version" : "Confirm requirements"}
			</Button>
		</div>
	</div>
);

type UploadTabProps = {
	confirmed: boolean;
	resumes: File[];
	uploadInputKey: number;
	setResumes: (files: File[]) => void;
	onSubmit: (event: FormEvent<HTMLFormElement>) => void;
	onConfirmCriteria: () => void;
};

const UploadTab = ({
	confirmed,
	resumes,
	uploadInputKey,
	setResumes,
	onSubmit,
	onConfirmCriteria,
}: UploadTabProps) => (
	<div className="workspace-stage-gap">
		{!confirmed && (
			<div className="upload-warning">
				Criteria are not confirmed yet.{" "}
				<button
					className="link-button"
					onClick={onConfirmCriteria}
					type="button"
				>
					Confirm criteria first
				</button>{" "}
				so uploads are scored against a locked version.
			</div>
		)}
		<form className="upload-panel" onSubmit={onSubmit}>
			<h3>Queue resume submissions</h3>
			<div className="form-field">
				<Label htmlFor="resume-files">Resume documents or ZIP</Label>
				<Input
					accept=".pdf,.docx,.txt,.zip"
					id="resume-files"
					key={uploadInputKey}
					multiple
					onChange={(event) =>
						setResumes(Array.from(event.currentTarget.files ?? []))
					}
					required
					type="file"
				/>
				<p className="form-hint">
					Choose multiple PDF, DOCX, or TXT files, or exactly one ZIP
					archive. Candidate names come from the resumes.
				</p>
			</div>
			<Button disabled={resumes.length === 0 || !confirmed} type="submit">
				<UploadCloud />
				Queue {resumes.length || "selected"} resume
				{resumes.length === 1 ? "" : "s"}
			</Button>
		</form>
	</div>
);

const EvidenceDrawer = ({
	evaluation,
	onClose,
}: {
	evaluation: Evaluation;
	onClose: () => void;
}) => (
	<div className="drawer-panel">
		<header className="drawer-head">
			<div>
				<p className="eyebrow">Evidence inspection</p>
				<h2 id="evidence-title">
					{evaluation.candidateName ?? "Candidate"}
				</h2>
				<div className="drawer-stats">
					<span className="score-cell">
						{evaluation.score ?? "—"}
						<span className="score-denominator">/100</span>
					</span>
					<span
						className={eligibilityChipClass(evaluation.eligibility)}
					>
						{evaluation.eligibility.replace(/_/g, " ")}
					</span>
					{evaluation.candidateEmail && (
						<span className="muted-copy">
							{evaluation.candidateEmail}
						</span>
					)}
					{evaluation.candidateLocation && (
						<span className="muted-copy">
							{evaluation.candidateLocation}
						</span>
					)}
				</div>
			</div>
			<button
				aria-label="Close evidence inspection"
				className="icon-button"
				onClick={onClose}
				type="button"
			>
				<X />
			</button>
		</header>

		{(evaluation.assessments ?? []).length === 0 ? (
			<p className="muted-copy">
				Evaluations appear here once processing completes.
			</p>
		) : (
			evaluation.assessments.map((assessment) => (
				<div className="assessment-card" key={assessment.requirement}>
					<div className="assessment-top">
						<p>{assessment.requirement}</p>
						<span className={outcomeChipClass(assessment.outcome)}>
							{assessment.outcome.replace(/_/g, " ")}
						</span>
					</div>
					<p className="assessment-reasoning">
						{assessment.reasoning}
					</p>
					{assessment.evidence.length > 0 && (
						<div className="assessment-evidence">
							{assessment.evidence.map((item) => (
								<blockquote
									className="evidence-quote"
									key={`${item.blockId}-${item.quote}`}
								>
									“{item.quote}”
									<cite>Source block: {item.blockId}</cite>
								</blockquote>
							))}
						</div>
					)}
				</div>
			))
		)}
	</div>
);
