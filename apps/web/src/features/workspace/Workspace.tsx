import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { Textarea } from "@skillsignal/ui/components/textarea";
import {
	ArrowDown,
	ArrowUp,
	Briefcase,
	CheckCircle2,
	ChevronRight,
	Copy,
	Download,
	FileText,
	Link as LinkIcon,
	Plus,
	UploadCloud,
	X,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";
import { authClient } from "../../lib/auth-client";
import {
	billingClient,
	type Evaluation,
	type EvaluationFilters,
	EXPORT_COLUMNS,
	type ExportColumn,
	type Job,
	type JobDetail,
	type JoinPolicy,
	type Member,
	type Organization,
	type OrgPoints,
	type PointPack,
	type Requirement,
	workspaceClient,
} from "./client";

type RazorpayCheckout = { open: () => void };

type RazorpayHandlerResponse = {
	razorpay_payment_id: string;
	razorpay_signature: string;
};

declare global {
	interface Window {
		Razorpay?: new (options: Record<string, unknown>) => RazorpayCheckout;
	}
}

type TabName = "results" | "criteria" | "upload";

type EligibilityFilter = "all" | "top" | Evaluation["eligibility"];
type OutcomeFilter = "all" | "met" | "partial" | "not_met" | "unknown";
type StatusFilter = "all" | "pending" | "processing" | "complete" | "failed";

type Invitation = {
	token: string;
	passcode: string;
	expiresAt: string;
};

type WindowStatus = { label: string; className: string };

const ENTERPRISE_SALES_EMAIL = "sales@skillsignal.app";

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
		kind:
			requirement.assessability === "resume_evidence"
				? requirement.suggestedKind
				: "ignored",
		weight: requirement.suggestedWeight,
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
	const [organizationName, setOrganizationName] = useState("");
	const [jobTitle, setJobTitle] = useState("");
	const [description, setDescription] = useState("");
	const [descriptionFile, setDescriptionFile] = useState<File | null>(null);
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
	const [joinPolicy, setJoinPolicy] = useState<JoinPolicy | null>(null);
	const [policyDomain, setPolicyDomain] = useState("");
	const [policyEmail, setPolicyEmail] = useState("");
	const [orgPoints, setOrgPoints] = useState<OrgPoints | null>(null);
	const [orgPacks, setOrgPacks] = useState<PointPack[]>([]);
	const [evaluationQuery, setEvaluationQuery] = useState("");
	const [eligibilityFilter, setEligibilityFilter] =
		useState<EligibilityFilter>("top");
	const [outcomeFilter, setOutcomeFilter] = useState<OutcomeFilter>("all");
	const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
	const [skillFilter, setSkillFilter] = useState("");
	const [minimumScoreText, setMinimumScoreText] = useState("");
	const [isExportOpen, setIsExportOpen] = useState(false);
	const [exportSelection, setExportSelection] = useState<ExportColumn[]>([
		...EXPORT_COLUMNS,
	]);
	const [exportLabels, setExportLabels] = useState<
		Partial<Record<ExportColumn, string>>
	>({});
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

	const moveExportColumn = (column: ExportColumn, delta: number) => {
		setExportSelection((current) => {
			const index = current.indexOf(column);
			const target = index + delta;
			if (index < 0 || target < 0 || target >= current.length) {
				return current;
			}
			const next = [...current];
			next.splice(index, 1);
			next.splice(target, 0, column);
			return next;
		});
	};

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

	const currentOrg = organization;

	const createOrganization = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!organizationName.trim()) return;
		try {
			const created =
				await workspaceClient.createOrganization(organizationName);
			setOrganizationName("");
			setIsCreateOrgOpen(false);
			setOrganization(created);
			setNotice("Employer organization created.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const createJob = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (
			!jobTitle.trim() ||
			!organizationId ||
			(!description.trim() && !descriptionFile)
		) {
			return;
		}
		try {
			const job = await workspaceClient.createJob(
				organizationId,
				jobTitle,
				description,
				descriptionFile,
			);
			const detail = await workspaceClient.job(job.id);
			setSelectedJob(detail);
			setRequirements(draftsToRequirements(detail));
			setJobTitle("");
			setDescription("");
			setDescriptionFile(null);
			setIsCreateJobOpen(false);
			setActiveTab("criteria");
			setJobs(await workspaceClient.jobs(organizationId));
			setNotice(
				"Role created. Requirement extraction is running before recruiter review.",
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
			if (currentOrg?.role === "owner") {
				setJoinPolicy(await workspaceClient.joinPolicy(organizationId));
			}
			billingClient
				.orgPoints(organizationId)
				.then(setOrgPoints)
				.catch(() => setOrgPoints(null));
			billingClient
				.packs()
				.then(setOrgPacks)
				.catch(() => setOrgPacks([]));
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

	const refreshJoinPolicy = async () => {
		setJoinPolicy(await workspaceClient.joinPolicy(organizationId));
	};

	const buyOrgPoints = async (packId: string) => {
		setError(null);
		try {
			await new Promise<void>((resolve, reject) => {
				if (window.Razorpay) return resolve();
				const script = document.createElement("script");
				script.src = "https://checkout.razorpay.com/v1/checkout.js";
				script.onload = () => resolve();
				script.onerror = () =>
					reject(new Error("Payment checkout could not be loaded"));
				document.head.appendChild(script);
			});
			const order = await billingClient.createOrder(
				packId,
				organizationId,
			);
			if (!window.Razorpay)
				throw new Error("Payment checkout unavailable");
			const checkout = new window.Razorpay({
				key: order.razorpayKeyId,
				order_id: order.razorpayOrderId,
				amount: order.amountInr * 100,
				currency: order.currency,
				name: "SkillSignal organization points",
				description: `${order.points} points`,
				theme: { color: "#111111" },
				handler: async (response: RazorpayHandlerResponse) => {
					try {
						await billingClient.verifyCheckout(
							order.id,
							response.razorpay_payment_id,
							response.razorpay_signature,
						);
						setOrgPoints(
							await billingClient.orgPoints(organizationId),
						);
					} catch (reason) {
						reportError(reason);
					}
				},
			});
			checkout.open();
		} catch (reason) {
			reportError(reason);
		}
	};

	const changeDefaultRole = async (
		defaultRole: JoinPolicy["defaultRole"],
	) => {
		try {
			await workspaceClient.setJoinPolicyDefaultRole(
				organizationId,
				defaultRole,
			);
			await refreshJoinPolicy();
			setNotice("Join policy updated.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const addPolicyDomain = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!policyDomain.trim()) return;
		try {
			const added = await workspaceClient.addJoinPolicyDomain(
				organizationId,
				policyDomain,
			);
			setPolicyDomain("");
			await refreshJoinPolicy();
			setNotice(`@${added.domain} can now join.`);
		} catch (reason) {
			reportError(reason);
		}
	};

	const removePolicyDomain = async (domain: string) => {
		try {
			await workspaceClient.removeJoinPolicyDomain(
				organizationId,
				domain,
			);
			await refreshJoinPolicy();
			setNotice("Domain rule removed. Existing members keep access.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const addPolicyEmail = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!policyEmail.trim()) return;
		try {
			const added = await workspaceClient.addJoinPolicyEmail(
				organizationId,
				policyEmail,
			);
			setPolicyEmail("");
			await refreshJoinPolicy();
			setNotice(`${added.email} can now join.`);
		} catch (reason) {
			reportError(reason);
		}
	};

	const removePolicyEmail = async (email: string) => {
		try {
			await workspaceClient.removeJoinPolicyEmail(organizationId, email);
			await refreshJoinPolicy();
			setNotice("Email rule removed. Existing members keep access.");
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
			await workspaceClient.exportEvaluationsCsv(selectedJob.id, {
				columns: exportSelection,
				labels: exportSelection.map(
					(column) => exportLabels[column]?.trim() || column,
				),
			});
			setIsExportOpen(false);
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
									exportCsv={() => setIsExportOpen(true)}
									minimumScoreText={minimumScoreText}
									onInspect={setInspectingEvaluation}
									onQueue={() => setActiveTab("upload")}
									visibleEvaluations={visibleEvaluations}
									{...{
										setEligibilityFilter,
										setEvaluationQuery,
										setMinimumScoreText,
										setOutcomeFilter,
										setSkillFilter,
										setStatusFilter,
									}}
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
								placeholder={
									descriptionFile
										? "Using the uploaded file. Clear it to paste instead."
										: "Paste the full description. Draft criteria are extracted automatically."
								}
								value={description}
							/>
							<Input
								accept=".pdf,.docx,.txt"
								id="create-job-description-file"
								onChange={(event) => {
									const selected =
										event.currentTarget.files?.[0] ?? null;
									setDescriptionFile(selected);
									if (selected) setDescription("");
								}}
								type="file"
							/>
							<p className="form-hint">
								Paste a description or upload a PDF, DOCX, or
								TXT file.
							</p>
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
								<p className="muted-copy loading-inline">
									<ThinkingOrb
										aria-hidden
										size={20}
										state="solving"
									/>
									Loading members...
								</p>
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
						{currentOrg?.role === "owner" && joinPolicy && (
							<div className="join-policy">
								<h4 className="join-policy-title">Access</h4>
								<p className="muted-copy">
									New employer accounts matching a rule below
									join this organization automatically with
									the default role. Removing a rule never
									removes existing members.
								</p>
								<div className="member-row">
									<span style={{ fontWeight: 600 }}>
										Default role for new members
									</span>
									<select
										aria-label="Default member role"
										className="workspace-filter-select"
										onChange={(event) =>
											void changeDefaultRole(
												event.target
													.value as JoinPolicy["defaultRole"],
											)
										}
										value={joinPolicy.defaultRole}
									>
										<option value="recruiter">
											Recruiter
										</option>
										<option value="viewer">Viewer</option>
									</select>
								</div>
								{joinPolicy.domains.length > 0 && (
									<div className="member-list">
										{joinPolicy.domains.map((domain) => (
											<div
												className="member-row"
												key={domain}
											>
												<span className="candidate-email">
													@{domain}
												</span>
												<span className="member-side">
													<Button
														onClick={() =>
															void removePolicyDomain(
																domain,
															)
														}
														size="sm"
														variant="outline"
													>
														Remove
													</Button>
												</span>
											</div>
										))}
									</div>
								)}
								<form
									className="member-form"
									onSubmit={addPolicyDomain}
								>
									<Input
										aria-label="Allowed email domain"
										onChange={(event) =>
											setPolicyDomain(event.target.value)
										}
										placeholder="@company.com"
										value={policyDomain}
									/>
									<Button size="sm" type="submit">
										<Plus />
										Allow domain
									</Button>
								</form>
								{joinPolicy.emails.length > 0 && (
									<div className="member-list">
										{joinPolicy.emails.map((email) => (
											<div
												className="member-row"
												key={email}
											>
												<span className="candidate-email">
													{email}
												</span>
												<span className="member-side">
													<Button
														onClick={() =>
															void removePolicyEmail(
																email,
															)
														}
														size="sm"
														variant="outline"
													>
														Remove
													</Button>
												</span>
											</div>
										))}
									</div>
								)}
								<form
									className="member-form"
									onSubmit={addPolicyEmail}
								>
									<Input
										aria-label="Allowed email address"
										onChange={(event) =>
											setPolicyEmail(event.target.value)
										}
										placeholder="contractor@personal.org"
										type="email"
										value={policyEmail}
									/>
									<Button size="sm" type="submit">
										<Plus />
										Allow email
									</Button>
								</form>
							</div>
						)}
						{orgPoints && (
							<div className="join-policy">
								<h4 className="join-policy-title">Points</h4>
								<p className="muted-copy">
									Evaluating one resume reserves up to the
									quoted maximum from this balance.{" "}
									{orgPoints.enterprise
										? "An enterprise entitlement covers batch evaluations without points."
										: "Contact sales for organization-wide enterprise access."}
								</p>
								<div className="member-row">
									<span style={{ fontWeight: 600 }}>
										{`${orgPoints.balance} points available`}
									</span>
								</div>
								{currentOrg?.role === "owner" &&
									orgPacks.length > 0 && (
										<form className="member-form">
											<select
												aria-label="Point pack"
												className="workspace-filter-select"
												id="org-point-pack"
												defaultValue={
													orgPacks[0]?.id ?? ""
												}
											>
												{orgPacks.map((pack) => (
													<option
														key={pack.id}
														value={pack.id}
													>{`${pack.points.toLocaleString()} points · ₹${pack.amountInr}`}</option>
												))}
											</select>
											<Button
												onClick={() => {
													const select =
														document.getElementById(
															"org-point-pack",
														) as HTMLSelectElement | null;
													if (select)
														void buyOrgPoints(
															select.value,
														);
												}}
												size="sm"
												type="button"
											>
												Buy points
											</Button>
										</form>
									)}
								{!orgPoints.enterprise && (
									<a
										className="candidate-email"
										href={`mailto:${ENTERPRISE_SALES_EMAIL}`}
									>
										Contact sales about enterprise access
									</a>
								)}
							</div>
						)}
					</div>
				</div>
			)}

			{isExportOpen && (
				<div
					{...overlayBackdrop({
						labelledBy: "export-title",
						onDismiss: () => setIsExportOpen(false),
					})}
				>
					<div className="modal-panel">
						<h3 id="export-title">Export CSV</h3>
						<p className="muted-copy">
							Choose, reorder, and rename the exported columns.
						</p>
						<ul className="export-columns">
							{EXPORT_COLUMNS.filter((column) =>
								exportSelection.includes(column),
							).map((column, index) => (
								<li className="export-column-row" key={column}>
									<span className="export-column-index">
										{index + 1}
									</span>
									<Input
										aria-label={`Rename ${column}`}
										onChange={(event) =>
											setExportLabels((current) => ({
												...current,
												[column]: event.target.value,
											}))
										}
										placeholder={column}
										value={exportLabels[column] ?? ""}
									/>
									<Button
										aria-label={`Move ${column} up`}
										disabled={index === 0}
										onClick={() =>
											moveExportColumn(column, -1)
										}
										size="icon-xs"
										variant="ghost"
									>
										<ArrowUp />
									</Button>
									<Button
										aria-label={`Move ${column} down`}
										disabled={
											index === exportSelection.length - 1
										}
										onClick={() =>
											moveExportColumn(column, 1)
										}
										size="icon-xs"
										variant="ghost"
									>
										<ArrowDown />
									</Button>
									<Button
										aria-label={`Remove ${column}`}
										onClick={() =>
											setExportSelection((current) =>
												current.filter(
													(selected) =>
														selected !== column,
												),
											)
										}
										size="icon-xs"
										variant="ghost"
									>
										<X />
									</Button>
								</li>
							))}
						</ul>
						{EXPORT_COLUMNS.filter(
							(column) => !exportSelection.includes(column),
						).length > 0 && (
							<select
								aria-label="Add export column"
								className="workspace-filter-select"
								onChange={(event) => {
									const value = event.target
										.value as ExportColumn;
									if (value) {
										setExportSelection((current) => [
											...current,
											value,
										]);
									}
									event.target.value = "";
								}}
								value=""
							>
								<option value="">Add column...</option>
								{EXPORT_COLUMNS.filter(
									(column) =>
										!exportSelection.includes(column),
								).map((column) => (
									<option key={column} value={column}>
										{column}
									</option>
								))}
							</select>
						)}
						<div className="modal-actions">
							<Button
								onClick={() => setIsExportOpen(false)}
								size="sm"
								type="button"
								variant="outline"
							>
								Cancel
							</Button>
							<Button
								disabled={exportSelection.length === 0}
								onClick={() => void exportCsv()}
								size="sm"
							>
								<Download />
								Export
							</Button>
						</div>
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
	outcomeFilter: OutcomeFilter;
	statusFilter: StatusFilter;
	skillFilter: string;
	minimumScoreText: string;
	setEvaluationQuery: (value: string) => void;
	setEligibilityFilter: (value: EligibilityFilter) => void;
	setOutcomeFilter: (value: OutcomeFilter) => void;
	setStatusFilter: (value: StatusFilter) => void;
	setSkillFilter: (value: string) => void;
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
	outcomeFilter,
	statusFilter,
	skillFilter,
	minimumScoreText,
	setEvaluationQuery,
	setEligibilityFilter,
	setOutcomeFilter,
	setStatusFilter,
	setSkillFilter,
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
						<option value="top">Top matches</option>
						<option value="all">All outcomes</option>
						<option value="eligible">Eligible</option>
						<option value="needs_review">Needs review</option>
						<option value="not_eligible">Not eligible</option>
					</select>
					<select
						aria-label="Filter by requirement outcome"
						className="workspace-filter-select"
						onChange={(event) =>
							setOutcomeFilter(
								event.target.value as OutcomeFilter,
							)
						}
						value={outcomeFilter}
					>
						<option value="all">Any requirement outcome</option>
						<option value="met">Has met requirement</option>
						<option value="partial">Has partial requirement</option>
						<option value="not_met">Has unmet requirement</option>
						<option value="unknown">Has unknown requirement</option>
					</select>
					<select
						aria-label="Filter by processing state"
						className="workspace-filter-select"
						onChange={(event) =>
							setStatusFilter(event.target.value as StatusFilter)
						}
						value={statusFilter}
					>
						<option value="all">Any processing state</option>
						<option value="pending">Pending</option>
						<option value="processing">Processing</option>
						<option value="complete">Complete</option>
						<option value="failed">Failed</option>
					</select>
					<Input
						aria-label="Filter by skill"
						onChange={(event) => setSkillFilter(event.target.value)}
						placeholder="Skill..."
						value={skillFilter}
					/>
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
							<th scope="col">Hard gates</th>
							<th scope="col">Evidence coverage</th>
							<th scope="col">Data quality</th>
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
									) : evaluation.qualityState ===
										"review_required" ? (
										<span className="muted-copy">
											Review required
										</span>
									) : evaluation.status === "complete" ||
										evaluation.status === "failed" ? (
										<span className="muted-copy">—</span>
									) : (
										<span className="pending-cell">
											<ThinkingOrb
												aria-hidden
												size={20}
												state="solving"
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
									<HardGateSummary
										gates={evaluation.hardGates ?? []}
									/>
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
								<td>
									<span className="quality-cell">
										{(
											evaluation.qualityState ?? "pending"
										).replace(/_/g, " ")}
										{(evaluation.qualityWarnings?.length ??
											0) > 0 && (
											<small>
												{evaluation.qualityWarnings
													?.length ?? 0}{" "}
												warning
												{evaluation.qualityWarnings
													?.length === 1
													? ""
													: "s"}
											</small>
										)}
									</span>
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
								<td colSpan={7}>
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
	draftStatus: JobDetail["draftStatus"];
	draftError: string | null;
	draftWarnings: string[];
	draftDegraded: boolean;
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
	draftStatus,
	draftError,
	draftWarnings,
	draftDegraded,
	onChange,
	onAdd,
	onConfirm,
}: CriteriaTabProps) => (
	<div className="workspace-stage-gap">
		<p className="criterion-note">
			Review every extracted criterion against its source. Only
			resume-evidence criteria can enter automated scoring. Hard gates
			remain a recruiter decision and only an evidenced failure can make
			an evaluation ineligible.
		</p>
		{draftStatus === "processing" && (
			<div className="criterion-processing" role="status">
				<ThinkingOrb aria-hidden size={20} state="solving" />
				Compiling requirements and checking source evidence...
			</div>
		)}
		{draftStatus === "failed" && (
			<p className="criterion-warning" role="alert">
				{draftError ??
					"The job description could not be processed. Upload a clearer digital document."}
			</p>
		)}
		{draftDegraded && (
			<p className="criterion-warning">
				Model extraction was unavailable. Review the deterministic draft
				carefully.
			</p>
		)}
		{draftWarnings.length > 0 && (
			<ul className="criterion-warnings">
				{draftWarnings.map((warning) => (
					<li key={warning}>{warning}</li>
				))}
			</ul>
		)}
		<div className="criterion-list">
			{requirements.map((requirement, index) => (
				<div className="criterion-row" key={requirement.stableId}>
					<span className="criterion-index">
						{(index + 1).toString().padStart(2, "0")}
					</span>
					<div className="criterion-content">
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
						<div className="criterion-metadata">
							<span>
								{formatRequirementLabel(requirement.category)}
							</span>
							<span>
								{formatRequirementLabel(
									requirement.assessability,
								)}
							</span>
							{requirement.predicate?.operator === "any_of" && (
								<span>alternative paths</span>
							)}
							{requirement.confidence !== undefined && (
								<span>
									{Math.round(requirement.confidence * 100)}%
									extraction confidence
								</span>
							)}
						</div>
						{(requirement.evidence ??
							requirement.sourceEvidence)?.[0] && (
							<blockquote className="criterion-source">
								"
								{
									(requirement.evidence ??
										requirement.sourceEvidence)?.[0]?.quote
								}
								"
							</blockquote>
						)}
					</div>
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
							<option
								disabled={
									requirement.assessability !==
									"resume_evidence"
								}
								value="hard_gate"
							>
								Hard gate
							</option>
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

const formatRequirementLabel = (value?: string) =>
	value ? value.replaceAll("_", " ") : "manual criterion";

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

const HardGateSummary = ({
	gates,
}: {
	gates: Array<{ requirement: string; outcome: string }>;
}) => {
	if (gates.length === 0) {
		return <span className="muted-copy">—</span>;
	}
	const failed = gates.filter((gate) => gate.outcome === "not_met").length;
	const attention = gates.filter(
		(gate) => gate.outcome === "partial" || gate.outcome === "unknown",
	).length;
	if (failed > 0) {
		return (
			<span className="gate-chip gate-failed">
				{failed} gate{failed === 1 ? "" : "s"} failed
			</span>
		);
	}
	if (attention > 0) {
		return (
			<span className="gate-chip gate-review">
				{attention} need{attention === 1 ? "s" : ""} review
			</span>
		);
	}
	return (
		<span className="gate-chip gate-met">
			{gates.length} gate{gates.length === 1 ? "" : "s"} met
		</span>
	);
};

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

		{(evaluation.qualityWarnings?.length ?? 0) > 0 && (
			<section className="drawer-quality" aria-labelledby="quality-title">
				<h3 id="quality-title">Data quality</h3>
				<ul>
					{evaluation.qualityWarnings?.map((warning) => (
						<li key={warning}>{warning}</li>
					))}
				</ul>
				{evaluation.extractionMetadata?.pageCount !== undefined && (
					<p>
						{evaluation.extractionMetadata?.pageCount} page
						{evaluation.extractionMetadata?.pageCount === 1
							? ""
							: "s"}
						, {evaluation.extractionMetadata?.blockCount ?? 0}{" "}
						evidence blocks
					</p>
				)}
			</section>
		)}

		{(evaluation.hardGates?.length ?? 0) > 0 && (
			<section className="drawer-quality" aria-labelledby="gates-title">
				<h3 id="gates-title">Hard gates</h3>
				<ul>
					{evaluation.hardGates?.map((gate) => (
						<li key={gate.requirement}>
							{gate.requirement} —{" "}
							{gate.outcome.replace(/_/g, " ")}
						</li>
					))}
				</ul>
			</section>
		)}

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
					{(assessment.kind === "hard_gate" ||
						assessment.contribution != null) && (
						<p className="assessment-weight">
							{assessment.kind === "hard_gate"
								? "Hard gate, excluded from the score"
								: `Weight ${assessment.weight ?? 1} · ${
										assessment.contribution
									}% of the score`}
						</p>
					)}
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
					{assessment.semanticEvidence?.matches?.length ? (
						<div className="assessment-evidence">
							<p className="eyebrow">Related passages</p>
							{assessment.semanticEvidence.matches.map(
								(match) => (
									<blockquote
										className="evidence-quote"
										key={`semantic-${match.blockId}`}
									>
										{match.text || match.blockId}
										<cite>
											Similarity{" "}
											{Math.round(match.similarity * 100)}
											%
										</cite>
									</blockquote>
								),
							)}
						</div>
					) : null}
				</div>
			))
		)}
	</div>
);
