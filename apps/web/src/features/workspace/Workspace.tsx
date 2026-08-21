import { Badge } from "@resume-screener/ui/components/badge";
import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { Textarea } from "@resume-screener/ui/components/textarea";
import {
	Briefcase,
	CheckCircle2,
	ChevronRight,
	Copy,
	FileText,
	Filter,
	Link as LinkIcon,
	Plus,
	Search,
	Sliders,
	Sparkles,
	UploadCloud,
	Users,
	X,
} from "lucide-react";
import { type FormEvent, useEffect, useState } from "react";
import { authClient } from "../../lib/auth-client";
import {
	type Evaluation,
	type Job,
	type JobDetail,
	type Organization,
	type Requirement,
	workspaceClient,
} from "./client";

const draftsToRequirements = (job: JobDetail): Requirement[] =>
	job.draftRequirements.map((requirement) => ({
		...requirement,
		kind: "required",
		weight: 2,
	}));

export const Workspace = () => {
	const { data: session, isPending } = authClient.useSession();
	const [organizations, setOrganizations] = useState<Organization[]>([]);
	const [organizationId, setOrganizationId] = useState("");
	const [jobs, setJobs] = useState<Job[]>([]);
	const [jobSearch, setJobSearch] = useState("");
	const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
	const [activeTab, setActiveTab] = useState<
		"results" | "criteria" | "upload"
	>("results");
	const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
	const [inspectingEvaluation, setInspectingEvaluation] =
		useState<Evaluation | null>(null);
	const [isCreateOrgOpen, setIsCreateOrgOpen] = useState(false);
	const [isCreateJobOpen, setIsCreateJobOpen] = useState(false);
	const [organizationName, setOrganizationName] = useState("");
	const [jobTitle, setJobTitle] = useState("");
	const [description, setDescription] = useState("");
	const [requirements, setRequirements] = useState<Requirement[]>([]);
	const [candidateName, setCandidateName] = useState("");
	const [resume, setResume] = useState<File | null>(null);
	const [processingJobId, setProcessingJobId] = useState<string | null>(null);
	const [invitationToken, setInvitationToken] = useState<string | null>(null);
	const [copiedInvitation, setCopiedInvitation] = useState(false);
	const [evaluationQuery, setEvaluationQuery] = useState("");
	const [evaluationFilter, setEvaluationFilter] = useState("eligible");
	const [notice, setNotice] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const loadOrganizations = async () => {
		const records = await workspaceClient.organizations();
		setOrganizations(records);
		setOrganizationId((current) => current || records[0]?.id || "");
	};

	const loadJobs = async (id: string) => {
		if (!id) return;
		const list = await workspaceClient.jobs(id);
		setJobs(list);
		const firstJob = list[0];
		if (firstJob && (!selectedJob || selectedJob.organizationId !== id)) {
			await openJob(firstJob);
		} else if (list.length === 0) {
			setSelectedJob(null);
		}
	};

	useEffect(() => {
		if (!session?.user) return;
		void workspaceClient
			.organizations()
			.then((records) => {
				setOrganizations(records);
				const defaultId = records[0]?.id || "";
				setOrganizationId(defaultId);
			})
			.catch((reason: unknown) => {
				setNotice(null);
				setError(
					reason instanceof Error ? reason.message : "Request failed",
				);
			});
	}, [session?.user]);

	useEffect(() => {
		if (!organizationId) return;
		setInvitationToken(null);
		setInspectingEvaluation(null);
		void workspaceClient
			.jobs(organizationId)
			.then(async (list) => {
				setJobs(list);
				const firstJob = list[0];
				if (!firstJob) {
					setSelectedJob(null);
					setEvaluations([]);
					return;
				}
				const [detail, jobEvaluations] = await Promise.all([
					workspaceClient.job(firstJob.id),
					workspaceClient.evaluations(firstJob.id),
				]);
				setSelectedJob(detail);
				setEvaluations(jobEvaluations);
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
			})
			.catch((reason: unknown) => {
				setNotice(null);
				setError(
					reason instanceof Error ? reason.message : "Request failed",
				);
			});
	}, [organizationId]);

	useEffect(() => {
		if (!processingJobId) return;
		const poll = () => {
			void workspaceClient
				.processingJob(processingJobId)
				.then((job) => {
					if (job.status === "completed") {
						setNotice("Resume processing completed successfully.");
						if (selectedJob) {
							void workspaceClient
								.evaluations(selectedJob.id)
								.then(setEvaluations);
						}
						setProcessingJobId(null);
					} else if (job.safeError || job.status === "failed") {
						setNotice(
							`Processing issue: ${job.safeError ?? "Failed"}`,
						);
						setProcessingJobId(null);
					} else {
						setNotice(`Resume evaluation status: ${job.status}...`);
					}
				})
				.catch((reason: unknown) => {
					setError(
						reason instanceof Error
							? reason.message
							: "Request failed",
					);
					setProcessingJobId(null);
				});
		};
		poll();
		const interval = window.setInterval(poll, 2_500);
		return () => window.clearInterval(interval);
	}, [processingJobId, selectedJob]);

	if (isPending) {
		return (
			<main className="app-shell flex items-center justify-center p-8">
				<div className="flex flex-col items-center gap-3 text-muted-foreground">
					<Sparkles className="size-6 animate-pulse text-accent" />
					<p className="text-sm font-mono">Loading workspace...</p>
				</div>
			</main>
		);
	}

	if (!session?.user) {
		return (
			<main className="app-shell flex items-center justify-center p-8">
				<div className="text-center space-y-4 max-w-sm">
					<p className="font-serif text-2xl">
						Sign in to access workspace
					</p>
					<Button asChild className="w-full">
						<a href="/sign-in">Sign in</a>
					</Button>
				</div>
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
			await loadOrganizations();
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
			await loadJobs(organizationId);
			setNotice(
				"Job created with extracted criteria. Confirm them to enable resume evaluations.",
			);
		} catch (reason) {
			reportError(reason);
		}
	};

	const openJob = async (job: Job) => {
		try {
			const detail = await workspaceClient.job(job.id);
			setSelectedJob(detail);
			const evals = await workspaceClient.evaluations(job.id);
			setEvaluations(evals);
			setInspectingEvaluation(null);
			setRequirements(
				detail.requirements.length
					? detail.requirements.map((requirement) => ({
							...requirement,
							normalizedText:
								requirement.text ?? requirement.normalizedText,
						}))
					: draftsToRequirements(detail),
			);
			setActiveTab(detail.confirmed ? "results" : "criteria");
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
			await loadJobs(organizationId);
			setNotice(
				"Requirements confirmed. Resume submissions are ready to process.",
			);
			setActiveTab("results");
		} catch (reason) {
			reportError(reason);
		}
	};

	const upload = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!selectedJob || !resume) return;
		try {
			const result = await workspaceClient.uploadResume(
				selectedJob.id,
				resume,
				candidateName,
			);
			setCandidateName("");
			setResume(null);
			setProcessingJobId(result.processingJobId);
			const updatedEvals = await workspaceClient.evaluations(
				selectedJob.id,
			);
			setEvaluations(updatedEvals);
			setNotice("Resume queued for async extraction and evaluation.");
			setActiveTab("results");
		} catch (reason) {
			reportError(reason);
		}
	};

	const handleCreateInvitation = async () => {
		if (!selectedJob) return;
		try {
			const inv = await workspaceClient.createInvitation(selectedJob.id);
			setInvitationToken(inv.token);
			setNotice("Invitation token generated.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const copyInvitationLink = () => {
		if (!invitationToken) return;
		const link = `${window.location.origin}/apply/${invitationToken}`;
		void navigator.clipboard.writeText(link);
		setCopiedInvitation(true);
		setTimeout(() => setCopiedInvitation(false), 2000);
	};

	const visibleEvaluations = evaluations.filter((evaluation) => {
		const query = evaluationQuery.trim().toLowerCase();
		const matchesQuery =
			!query ||
			(evaluation.candidateName ?? "Candidate")
				.toLowerCase()
				.includes(query);
		const matchesFilter =
			evaluationFilter === "all" ||
			evaluation.eligibility === evaluationFilter ||
			evaluation.status === evaluationFilter;
		return matchesQuery && matchesFilter;
	});

	const filteredJobs = jobs.filter((job) =>
		job.title.toLowerCase().includes(jobSearch.toLowerCase()),
	);
	const startCreateJob = () => {
		if (organizationId) setIsCreateJobOpen(true);
		else setIsCreateOrgOpen(true);
	};

	return (
		<div className="min-h-screen bg-[var(--bone)] text-[var(--ink)] flex flex-col font-sans">
			{/* Top Header */}
			<header className="border-b border-[var(--ink)] bg-[var(--bone)] sticky top-0 z-30 px-6 py-3 flex items-center justify-between gap-4">
				<div className="flex items-center gap-6">
					<a href="/" className="brand-mark flex items-center gap-2">
						<span className="size-7 rounded-sm border border-[var(--ink)] inline-flex items-center justify-center font-serif italic text-xs">
							rs
						</span>
						<span className="font-mono text-xs tracking-wider uppercase font-bold">
							resume screener
						</span>
					</a>

					<div className="h-4 w-px bg-[var(--rule)]" />

					{/* Organization Dropdown / Selector */}
					<div className="flex items-center gap-2">
						<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
							Org
						</span>
						<select
							value={organizationId}
							onChange={(e) => setOrganizationId(e.target.value)}
							className="bg-transparent text-xs font-semibold border border-[var(--rule)] rounded px-2.5 py-1 focus:border-[var(--ink)] outline-none"
						>
							{organizations.map((org) => (
								<option key={org.id} value={org.id}>
									{org.name} ({org.role})
								</option>
							))}
						</select>
						<Button
							size="xs"
							variant="outline"
							onClick={() => setIsCreateOrgOpen(true)}
							className="h-7 text-xs font-mono"
						>
							<Plus className="size-3 mr-1" /> New Org
						</Button>
					</div>
				</div>

				<div className="flex items-center gap-5">
					<div className="hidden sm:flex items-center gap-3 font-mono text-[11px] uppercase text-[var(--muted)]">
						<div className="flex items-center gap-1.5">
							<span className="size-2 rounded-full bg-emerald-600" />
							<span>Employer workspace</span>
						</div>
					</div>

					<div className="flex items-center gap-3 pl-4 border-l border-[var(--rule)]">
						<span className="font-mono text-xs font-medium">
							{session.user.name || session.user.email}
						</span>
						<Button
							size="xs"
							variant="outline"
							onClick={() => authClient.signOut()}
							className="font-mono text-[11px] h-7"
						>
							Sign out
						</Button>
					</div>
				</div>
			</header>

			{/* Notices / Banners */}
			{notice && (
				<div className="bg-[var(--soft)] border-b border-[var(--rule)] px-6 py-2 flex items-center justify-between text-xs font-mono">
					<span>{notice}</span>
					<button
						type="button"
						onClick={() => setNotice(null)}
						className="text-[var(--muted)] hover:text-[var(--ink)]"
					>
						<X className="size-3.5" />
					</button>
				</div>
			)}
			{error && (
				<div className="bg-rose-50 text-rose-800 border-b border-rose-200 px-6 py-2 flex items-center justify-between text-xs font-mono">
					<span>{error}</span>
					<button
						type="button"
						onClick={() => setError(null)}
						className="text-rose-500 hover:text-rose-800"
					>
						<X className="size-3.5" />
					</button>
				</div>
			)}

			{/* Main Workspace Layout */}
			<div className="flex-1 grid grid-cols-1 md:grid-cols-[300px_1fr] min-h-[calc(100vh-50px)]">
				{/* Left Sidebar: Job Library */}
				<aside className="border-r border-[var(--rule)] bg-[var(--bone)] p-4 flex flex-col gap-4">
					<div className="flex items-center justify-between">
						<div>
							<h2 className="font-serif text-lg font-normal">
								Roles
							</h2>
							<p className="text-[11px] font-mono text-[var(--muted)] uppercase">
								{jobs.length} total roles
							</p>
						</div>
						<Button
							size="sm"
							onClick={startCreateJob}
							className="h-8 font-mono text-xs bg-[var(--ink)] text-[var(--bone)] hover:bg-[var(--accent)]"
						>
							<Plus className="size-3.5 mr-1" /> New Job
						</Button>
					</div>

					<div className="relative">
						<Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
						<Input
							value={jobSearch}
							onChange={(e) => setJobSearch(e.target.value)}
							placeholder="Search roles..."
							className="h-8 pl-8 text-xs bg-white/40 border-[var(--rule)]"
						/>
					</div>

					{/* Job List */}
					<div className="flex-1 overflow-y-auto space-y-1">
						{filteredJobs.map((job) => {
							const isSelected = selectedJob?.id === job.id;
							return (
								<button
									key={job.id}
									type="button"
									onClick={() => void openJob(job)}
									className={`w-full text-left p-2.5 rounded transition-colors flex items-start justify-between gap-2 border ${
										isSelected
											? "bg-white border-[var(--ink)] shadow-xs"
											: "border-transparent hover:bg-white/50"
									}`}
								>
									<div className="min-w-0 space-y-1">
										<p className="text-xs font-semibold truncate leading-tight">
											{job.title}
										</p>
										<div className="flex items-center gap-2">
											<span
												className={`inline-flex items-center gap-1 text-[10px] font-mono uppercase ${
													job.confirmed
														? "text-emerald-700 font-medium"
														: "text-amber-700"
												}`}
											>
												<span
													className={`size-1.5 rounded-full ${
														job.confirmed
															? "bg-emerald-600"
															: "bg-amber-500"
													}`}
												/>
												{job.confirmed
													? "Confirmed"
													: "Draft"}
											</span>
										</div>
									</div>
									<ChevronRight className="size-3.5 text-[var(--muted)] shrink-0 mt-0.5" />
								</button>
							);
						})}

						{filteredJobs.length === 0 && (
							<div className="p-6 text-center text-xs text-[var(--muted)] space-y-2 border border-dashed border-[var(--rule)] rounded">
								<Briefcase className="size-5 mx-auto text-[var(--muted)]" />
								<p>No jobs found.</p>
								<Button
									size="xs"
									variant="outline"
									onClick={startCreateJob}
								>
									Create Role
								</Button>
							</div>
						)}
					</div>
				</aside>

				{/* Right Main Stage: Selected Job Workspace */}
				<main className="p-6 overflow-y-auto flex flex-col gap-6">
					{selectedJob ? (
						<>
							{/* Job Header & Actions */}
							<div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[var(--rule)]">
								<div className="space-y-1">
									<div className="flex items-center gap-2">
										<h1 className="font-serif text-2xl font-normal leading-tight">
											{selectedJob.title}
										</h1>
										<Badge
											variant={
												selectedJob.confirmed
													? "success"
													: "warning"
											}
											className="font-mono text-[10px] uppercase tracking-wider"
										>
											{selectedJob.confirmed
												? "Requirements Confirmed"
												: "Needs Confirmation"}
										</Badge>
									</div>
									<p className="text-xs text-[var(--muted)] font-mono">
										{currentOrg?.name} ·{" "}
										{evaluations.length} candidate
										submissions evaluated
									</p>
								</div>

								{/* Header Action Bar */}
								<div className="flex items-center gap-2">
									<Button
										size="sm"
										variant="outline"
										onClick={handleCreateInvitation}
										className="h-8 font-mono text-xs"
									>
										<LinkIcon className="size-3.5 mr-1" />{" "}
										Invite Candidate
									</Button>
									<Button
										size="sm"
										onClick={() => setActiveTab("upload")}
										className="h-8 font-mono text-xs bg-[var(--ink)] text-[var(--bone)] hover:bg-[var(--accent)]"
									>
										<UploadCloud className="size-3.5 mr-1" />{" "}
										Queue Resume
									</Button>
								</div>
							</div>

							{/* Invitation Token Card if generated */}
							{invitationToken && (
								<div className="bg-white border border-[var(--ink)] p-3 rounded flex items-center justify-between gap-3 text-xs font-mono">
									<div className="truncate">
										<span className="text-[var(--muted)] mr-2">
											Single-use Invitation Link:
										</span>
										<code className="bg-[var(--soft)] px-2 py-0.5 rounded">
											{`${window.location.origin}/apply/${invitationToken}`}
										</code>
									</div>
									<Button
										size="xs"
										variant="outline"
										onClick={copyInvitationLink}
										className="shrink-0 font-mono text-[11px]"
									>
										<Copy className="size-3 mr-1" />
										{copiedInvitation
											? "Copied"
											: "Copy Link"}
									</Button>
								</div>
							)}

							{/* Navigation Tabs */}
							<div className="flex items-center gap-6 border-b border-[var(--rule)] font-mono text-xs uppercase tracking-wider">
								<button
									type="button"
									onClick={() => setActiveTab("results")}
									className={`pb-2.5 border-b-2 transition-colors flex items-center gap-2 ${
										activeTab === "results"
											? "border-[var(--ink)] text-[var(--ink)] font-bold"
											: "border-transparent text-[var(--muted)] hover:text-[var(--ink)]"
									}`}
								>
									<Users className="size-3.5" />
									Top Matches ({evaluations.length})
								</button>
								<button
									type="button"
									onClick={() => setActiveTab("criteria")}
									className={`pb-2.5 border-b-2 transition-colors flex items-center gap-2 ${
										activeTab === "criteria"
											? "border-[var(--ink)] text-[var(--ink)] font-bold"
											: "border-transparent text-[var(--muted)] hover:text-[var(--ink)]"
									}`}
								>
									<Sliders className="size-3.5" />
									Criteria & Requirements (
									{requirements.length})
								</button>
								<button
									type="button"
									onClick={() => setActiveTab("upload")}
									className={`pb-2.5 border-b-2 transition-colors flex items-center gap-2 ${
										activeTab === "upload"
											? "border-[var(--ink)] text-[var(--ink)] font-bold"
											: "border-transparent text-[var(--muted)] hover:text-[var(--ink)]"
									}`}
								>
									<UploadCloud className="size-3.5" />
									Upload Resume
								</button>
							</div>

							{/* TAB 1: TOP MATCHES & SUBMISSIONS */}
							{activeTab === "results" && (
								<div className="space-y-4">
									{/* Quick stats strip */}
									<div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
										<div className="p-3 bg-white/60 border border-[var(--rule)] rounded">
											<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
												Evaluated
											</span>
											<p className="font-serif text-xl font-normal">
												{evaluations.length}
											</p>
										</div>
										<div className="p-3 bg-white/60 border border-[var(--rule)] rounded">
											<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
												Top Score
											</span>
											<p className="font-serif text-xl font-normal">
												{evaluations.find(
													(e) => e.score !== null,
												)?.score ?? "—"}{" "}
												<span className="text-xs font-mono text-[var(--muted)]">
													/ 100
												</span>
											</p>
										</div>
										<div className="p-3 bg-white/60 border border-[var(--rule)] rounded">
											<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
												Eligible
											</span>
											<p className="font-serif text-xl font-normal text-emerald-700">
												{
													evaluations.filter(
														(e) =>
															e.eligibility ===
															"eligible",
													).length
												}
											</p>
										</div>
										<div className="p-3 bg-white/60 border border-[var(--rule)] rounded">
											<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
												Needs Review
											</span>
											<p className="font-serif text-xl font-normal text-amber-700">
												{
													evaluations.filter(
														(e) =>
															e.eligibility ===
															"needs_review",
													).length
												}
											</p>
										</div>
									</div>

									{/* Filters Bar */}
									<div className="flex flex-col sm:flex-row items-center justify-between gap-3 bg-white/40 p-2.5 border border-[var(--rule)] rounded">
										<div className="relative w-full sm:w-72">
											<Search className="size-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-[var(--muted)]" />
											<Input
												value={evaluationQuery}
												onChange={(e) =>
													setEvaluationQuery(
														e.target.value,
													)
												}
												placeholder="Search candidate name..."
												className="h-8 pl-8 text-xs bg-white border-[var(--rule)]"
											/>
										</div>

										<div className="flex items-center gap-2 w-full sm:w-auto">
											<Filter className="size-3.5 text-[var(--muted)]" />
											<select
												value={evaluationFilter}
												onChange={(e) =>
													setEvaluationFilter(
														e.target.value,
													)
												}
												className="h-8 text-xs bg-white border border-[var(--rule)] rounded px-2.5 outline-none"
											>
												<option value="all">
													All Outcomes
												</option>
												<option value="eligible">
													Eligible Only
												</option>
												<option value="needs_review">
													Needs Review
												</option>
												<option value="not_eligible">
													Not Eligible
												</option>
											</select>
										</div>
									</div>

									{/* Candidates Data Table */}
									<div className="border border-[var(--rule)] bg-white rounded overflow-hidden">
										<table className="w-full text-left text-xs border-collapse">
											<thead>
												<tr className="border-b border-[var(--rule)] bg-[var(--soft)] font-mono text-[10px] uppercase text-[var(--muted)]">
													<th className="p-3 font-semibold">
														Candidate
													</th>
													<th className="p-3 font-semibold">
														Fit Score
													</th>
													<th className="p-3 font-semibold">
														Eligibility
													</th>
													<th className="p-3 font-semibold">
														Evidence Coverage
													</th>
													<th className="p-3 font-semibold text-right">
														Action
													</th>
												</tr>
											</thead>
											<tbody className="divide-y divide-[var(--rule)]">
												{visibleEvaluations.map(
													(evaluation) => {
														const score =
															evaluation.score;
														return (
															<tr
																key={
																	evaluation.id
																}
																className="hover:bg-[var(--bone)]/40 transition-colors"
															>
																<td className="p-3 font-medium">
																	{evaluation.candidateName ??
																		"Candidate"}
																</td>
																<td className="p-3">
																	{score !==
																	null ? (
																		<span className="font-mono font-bold text-sm">
																			{
																				score
																			}
																			<span className="text-[10px] text-[var(--muted)] font-normal">
																				/100
																			</span>
																		</span>
																	) : (
																		<span className="font-mono text-[var(--muted)]">
																			Processing
																		</span>
																	)}
																</td>
																<td className="p-3">
																	<Badge
																		variant={
																			evaluation.eligibility ===
																			"eligible"
																				? "success"
																				: evaluation.eligibility ===
																						"needs_review"
																					? "warning"
																					: "destructive"
																		}
																		className="font-mono text-[10px] uppercase"
																	>
																		{evaluation.eligibility.replace(
																			"_",
																			" ",
																		)}
																	</Badge>
																</td>
																<td className="p-3 font-mono text-xs">
																	{evaluation.coverage !==
																	null
																		? `${Math.round(evaluation.coverage * 100)}%`
																		: "—"}
																</td>
																<td className="p-3 text-right">
																	<Button
																		size="xs"
																		variant="outline"
																		onClick={() =>
																			setInspectingEvaluation(
																				evaluation,
																			)
																		}
																		className="font-mono text-[11px]"
																	>
																		Inspect
																		Evidence
																	</Button>
																</td>
															</tr>
														);
													},
												)}

												{visibleEvaluations.length ===
													0 && (
													<tr>
														<td
															colSpan={5}
															className="p-8 text-center text-xs text-[var(--muted)]"
														>
															{evaluations.length ===
															0 ? (
																<div className="space-y-3 max-w-sm mx-auto">
																	<FileText className="size-6 mx-auto text-[var(--muted)]" />
																	<p className="font-serif text-base text-[var(--ink)]">
																		No
																		candidate
																		resumes
																		evaluated
																		yet
																	</p>
																	<p className="text-[11px] font-mono text-[var(--muted)]">
																		Confirm
																		criteria
																		and
																		upload
																		candidate
																		resumes
																		to run
																		evidence-backed
																		comparisons.
																	</p>
																	<Button
																		size="sm"
																		onClick={() =>
																			setActiveTab(
																				"upload",
																			)
																		}
																	>
																		Queue
																		Resume
																	</Button>
																</div>
															) : (
																<p>
																	No
																	evaluations
																	match active
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
							)}

							{/* TAB 2: CRITERIA & REQUIREMENTS */}
							{activeTab === "criteria" && (
								<div className="space-y-4 max-w-4xl">
									<div className="p-3.5 bg-white border border-[var(--rule)] rounded text-xs space-y-1">
										<p className="font-semibold text-[var(--ink)]">
											Confirm criteria before screening
											resumes
										</p>
										<p className="text-[var(--muted)]">
											The AI extracts draft criteria from
											the job description. You can
											classify criteria as Required
											(weight 2), Preferred (weight 1), or
											a Hard Gate (Pass/Fail gate).
											Confirming creates an immutable
											version for all scoring.
										</p>
									</div>

									<div className="space-y-2">
										{requirements.map(
											(requirement, index) => (
												<div
													key={requirement.stableId}
													className="p-3 bg-white border border-[var(--rule)] rounded flex flex-col sm:flex-row items-start sm:items-center gap-3"
												>
													<span className="font-mono text-xs text-[var(--muted)] font-bold">
														{(index + 1)
															.toString()
															.padStart(2, "0")}
													</span>
													<Input
														value={
															requirement.normalizedText ??
															""
														}
														onChange={(e) =>
															setRequirements(
																(curr) =>
																	curr.map(
																		(
																			item,
																			i,
																		) =>
																			i ===
																			index
																				? {
																						...item,
																						normalizedText:
																							e
																								.target
																								.value,
																					}
																				: item,
																	),
															)
														}
														className="flex-1 text-xs"
														placeholder="Requirement statement..."
													/>
													<div className="flex items-center gap-2 shrink-0">
														<select
															value={
																requirement.kind
															}
															onChange={(e) =>
																setRequirements(
																	(curr) =>
																		curr.map(
																			(
																				item,
																				i,
																			) =>
																				i ===
																				index
																					? {
																							...item,
																							kind: e
																								.target
																								.value as Requirement["kind"],
																						}
																					: item,
																		),
																)
															}
															className="h-9 text-xs border border-[var(--rule)] rounded px-2.5 bg-white outline-none"
														>
															<option value="required">
																Required
															</option>
															<option value="preferred">
																Preferred
															</option>
															<option value="hard_gate">
																Hard Gate
															</option>
															<option value="ignored">
																Ignored
															</option>
														</select>
														<Input
															type="number"
															min={1}
															max={10}
															value={
																requirement.weight
															}
															onChange={(e) =>
																setRequirements(
																	(curr) =>
																		curr.map(
																			(
																				item,
																				i,
																			) =>
																				i ===
																				index
																					? {
																							...item,
																							weight: Number(
																								e
																									.target
																									.value,
																							),
																						}
																					: item,
																		),
																)
															}
															className="w-16 h-9 text-xs font-mono text-center"
															title="Weight (1-10)"
														/>
													</div>
												</div>
											),
										)}
									</div>

									<div className="flex items-center justify-between pt-2">
										<Button
											type="button"
											variant="outline"
											size="sm"
											onClick={() =>
												setRequirements((curr) => [
													...curr,
													{
														stableId: `custom_${Date.now()}`,
														normalizedText: "",
														kind: "required",
														weight: 2,
													},
												])
											}
											className="font-mono text-xs"
										>
											<Plus className="size-3.5 mr-1" />{" "}
											Add Criterion
										</Button>

										<Button
											onClick={() => void confirm()}
											disabled={requirements.length === 0}
											className="bg-[var(--ink)] text-[var(--bone)] hover:bg-[var(--accent)] font-mono text-xs"
										>
											<CheckCircle2 className="size-3.5 mr-1" />{" "}
											Confirm Requirements
										</Button>
									</div>
								</div>
							)}

							{/* TAB 3: UPLOAD RESUMES */}
							{activeTab === "upload" && (
								<div className="max-w-xl space-y-6">
									{!selectedJob.confirmed && (
										<div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 rounded text-xs">
											<strong>Note:</strong> Job criteria
											are not confirmed yet. Please
											confirm requirements before
											screening resumes.
										</div>
									)}

									<form
										onSubmit={upload}
										className="space-y-4 p-6 bg-white border border-[var(--rule)] rounded"
									>
										<h3 className="font-serif text-lg">
											Queue Resume Submission
										</h3>

										<div className="space-y-1.5">
											<Label
												htmlFor="candidate-name"
												className="text-xs"
											>
												Candidate Name (Optional)
											</Label>
											<Input
												id="candidate-name"
												value={candidateName}
												onChange={(e) =>
													setCandidateName(
														e.target.value,
													)
												}
												placeholder="e.g. Alex Johnson"
												className="text-xs"
											/>
										</div>

										<div className="space-y-1.5">
											<Label
												htmlFor="resume-file"
												className="text-xs"
											>
												Resume Document (PDF, DOCX, TXT)
											</Label>
											<Input
												id="resume-file"
												type="file"
												accept=".pdf,.docx,.txt"
												onChange={(e) =>
													setResume(
														e.currentTarget
															.files?.[0] ?? null,
													)
												}
												required
												className="text-xs file:font-mono file:text-xs"
											/>
											<p className="text-[11px] font-mono text-[var(--muted)]">
												Accepted digital documents up to
												20MB. Scanned or image PDFs are
												rejected.
											</p>
										</div>

										<Button
											type="submit"
											disabled={
												!resume ||
												!selectedJob.confirmed
											}
											className="w-full bg-[var(--ink)] text-[var(--bone)] hover:bg-[var(--accent)] font-mono text-xs"
										>
											<UploadCloud className="size-3.5 mr-1" />{" "}
											Queue for Evaluation
										</Button>
									</form>
								</div>
							)}
						</>
					) : (
						<div className="flex-1 flex flex-col items-center justify-center p-12 text-center text-[var(--muted)] space-y-4">
							<Briefcase className="size-10 text-[var(--muted)]" />
							<div className="space-y-1 max-w-sm">
								<h3 className="font-serif text-xl text-[var(--ink)]">
									{organizationId
										? "Select or create a role"
										: "Create your organization"}
								</h3>
								<p className="text-xs text-[var(--muted)] font-mono">
									{organizationId
										? "Choose a job from the sidebar to review candidates, inspect evidence, or confirm role criteria."
										: "An employer organization owns your jobs, candidate submissions, and evaluation points."}
								</p>
							</div>
							<Button size="sm" onClick={startCreateJob}>
								<Plus className="size-3.5 mr-1" />{" "}
								{organizationId
									? "Create first role"
									: "Create organization"}
							</Button>
						</div>
					)}
				</main>
			</div>

			{/* Modal: Create Organization */}
			{isCreateOrgOpen && (
				<div
					aria-labelledby="create-org-title"
					aria-modal="true"
					className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4"
					role="dialog"
				>
					<div className="bg-white border border-[var(--ink)] p-6 rounded shadow-lg max-w-md w-full space-y-4">
						<div className="flex items-center justify-between">
							<h3
								className="font-serif text-lg"
								id="create-org-title"
							>
								Create Organization
							</h3>
							<button
								type="button"
								onClick={() => setIsCreateOrgOpen(false)}
								className="text-[var(--muted)] hover:text-[var(--ink)]"
							>
								<X className="size-4" />
							</button>
						</div>
						<form
							onSubmit={createOrganization}
							className="space-y-3"
						>
							<div className="space-y-1">
								<Label htmlFor="org-name" className="text-xs">
									Organization Name
								</Label>
								<Input
									id="org-name"
									value={organizationName}
									onChange={(e) =>
										setOrganizationName(e.target.value)
									}
									placeholder="e.g. Acme Corp"
									required
									className="text-xs"
								/>
							</div>
							<div className="flex justify-end gap-2 pt-2">
								<Button
									type="button"
									variant="outline"
									size="sm"
									onClick={() => setIsCreateOrgOpen(false)}
								>
									Cancel
								</Button>
								<Button
									type="submit"
									size="sm"
									className="bg-[var(--ink)] text-[var(--bone)]"
								>
									Create Org
								</Button>
							</div>
						</form>
					</div>
				</div>
			)}

			{/* Modal: Create Job */}
			{isCreateJobOpen && (
				<div
					aria-labelledby="create-job-dialog-title"
					aria-modal="true"
					className="fixed inset-0 bg-black/40 backdrop-blur-xs z-50 flex items-center justify-center p-4"
					role="dialog"
				>
					<div className="bg-white border border-[var(--ink)] p-6 rounded shadow-lg max-w-lg w-full space-y-4">
						<div className="flex items-center justify-between">
							<h3
								className="font-serif text-xl"
								id="create-job-dialog-title"
							>
								Create New Role
							</h3>
							<button
								type="button"
								onClick={() => setIsCreateJobOpen(false)}
								className="text-[var(--muted)] hover:text-[var(--ink)]"
							>
								<X className="size-4" />
							</button>
						</div>
						<form onSubmit={createJob} className="space-y-3">
							<div className="space-y-1">
								<Label
									htmlFor="create-job-title"
									className="text-xs"
								>
									Role Title
								</Label>
								<Input
									id="create-job-title"
									value={jobTitle}
									onChange={(e) =>
										setJobTitle(e.target.value)
									}
									placeholder="e.g. Senior Frontend Engineer"
									required
									className="text-xs"
								/>
							</div>
							<div className="space-y-1">
								<Label
									htmlFor="create-job-desc"
									className="text-xs"
								>
									Job Description
								</Label>
								<Textarea
									id="create-job-desc"
									value={description}
									onChange={(e) =>
										setDescription(e.target.value)
									}
									placeholder="Paste the full job description. The AI will extract draft criteria automatically..."
									required
									className="min-h-36 text-xs font-mono"
								/>
							</div>
							<div className="flex justify-end gap-2 pt-2">
								<Button
									type="button"
									variant="outline"
									size="sm"
									onClick={() => setIsCreateJobOpen(false)}
								>
									Cancel
								</Button>
								<Button
									type="submit"
									size="sm"
									className="bg-[var(--ink)] text-[var(--bone)]"
								>
									Extract Criteria & Create
								</Button>
							</div>
						</form>
					</div>
				</div>
			)}

			{/* Evidence Inspection Drawer/Modal */}
			{inspectingEvaluation && (
				<div
					aria-labelledby="evidence-title"
					aria-modal="true"
					className="fixed inset-0 bg-black/50 backdrop-blur-xs z-50 flex items-center justify-end"
					role="dialog"
				>
					<div className="bg-[var(--bone)] border-l border-[var(--ink)] h-full w-full max-w-2xl p-6 overflow-y-auto space-y-6 shadow-2xl">
						<div className="flex items-start justify-between pb-4 border-b border-[var(--rule)]">
							<div>
								<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
									Evidence Inspection
								</span>
								<h2
									className="font-serif text-2xl"
									id="evidence-title"
								>
									{inspectingEvaluation.candidateName ??
										"Candidate"}
								</h2>
								<div className="flex items-center gap-3 mt-2">
									<span className="font-mono font-bold text-sm">
										Score:{" "}
										{inspectingEvaluation.score ??
											"Pending"}
										/100
									</span>
									<Badge
										variant={
											inspectingEvaluation.eligibility ===
											"eligible"
												? "success"
												: inspectingEvaluation.eligibility ===
														"needs_review"
													? "warning"
													: "destructive"
										}
										className="font-mono text-[10px] uppercase"
									>
										{inspectingEvaluation.eligibility.replace(
											"_",
											" ",
										)}
									</Badge>
									<span className="font-mono text-xs text-[var(--muted)]">
										Coverage:{" "}
										{inspectingEvaluation.coverage !== null
											? `${Math.round(inspectingEvaluation.coverage * 100)}%`
											: "—"}
									</span>
								</div>
							</div>
							<button
								type="button"
								onClick={() => setInspectingEvaluation(null)}
								className="text-[var(--muted)] hover:text-[var(--ink)] p-1"
							>
								<X className="size-5" />
							</button>
						</div>

						<div className="space-y-4">
							<h3 className="font-mono text-xs uppercase tracking-wider text-[var(--muted)]">
								Requirement Assessments (
								{inspectingEvaluation.assessments.length})
							</h3>

							{inspectingEvaluation.assessments.map(
								(assessment) => (
									<div
										key={assessment.requirement}
										className="p-4 bg-white border border-[var(--rule)] rounded space-y-2.5"
									>
										<div className="flex items-start justify-between gap-3">
											<p className="font-medium text-xs text-[var(--ink)]">
												{assessment.requirement}
											</p>
											<Badge
												variant={
													assessment.outcome === "met"
														? "success"
														: assessment.outcome ===
																"partial"
															? "warning"
															: "destructive"
												}
												className="font-mono text-[10px] uppercase shrink-0"
											>
												{assessment.outcome}
											</Badge>
										</div>

										<p className="text-xs text-[var(--muted)] leading-relaxed">
											{assessment.reasoning}
										</p>

										{assessment.evidence.length > 0 && (
											<div className="space-y-1.5 pt-1">
												<span className="font-mono text-[10px] uppercase text-[var(--muted)]">
													Quoted Resume Evidence:
												</span>
												{assessment.evidence.map(
													(evidence) => (
														<blockquote
															key={
																evidence.blockId
															}
															className="border-l-2 border-[var(--accent)] pl-3 py-1 bg-[var(--soft)]/40 text-xs italic font-serif"
														>
															“{evidence.quote}”
															<cite className="block mt-1 font-mono text-[10px] not-italic text-[var(--muted)]">
																Source block:{" "}
																{
																	evidence.blockId
																}
															</cite>
														</blockquote>
													),
												)}
											</div>
										)}
									</div>
								),
							)}
						</div>
					</div>
				</div>
			)}
		</div>
	);

	function reportError(reason: unknown) {
		setNotice(null);
		setError(reason instanceof Error ? reason.message : "Request failed");
	}
};
