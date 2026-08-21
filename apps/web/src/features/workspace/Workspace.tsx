import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
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
	const [selectedJob, setSelectedJob] = useState<JobDetail | null>(null);
	const [evaluations, setEvaluations] = useState<Evaluation[]>([]);
	const [openEvaluationId, setOpenEvaluationId] = useState<string | null>(
		null,
	);
	const [organizationName, setOrganizationName] = useState("");
	const [jobTitle, setJobTitle] = useState("");
	const [description, setDescription] = useState("");
	const [requirements, setRequirements] = useState<Requirement[]>([]);
	const [candidateName, setCandidateName] = useState("");
	const [resume, setResume] = useState<File | null>(null);
	const [processingJobId, setProcessingJobId] = useState<string | null>(null);
	const [notice, setNotice] = useState<string | null>(null);
	const [error, setError] = useState<string | null>(null);

	const loadOrganizations = async () => {
		const records = await workspaceClient.organizations();
		setOrganizations(records);
		setOrganizationId((current) => current || records[0]?.id || "");
	};

	const loadJobs = async (id: string) => {
		if (!id) return;
		setJobs(await workspaceClient.jobs(id));
	};

	useEffect(() => {
		if (!session?.user) return;
		void workspaceClient
			.organizations()
			.then((records) => {
				setOrganizations(records);
				setOrganizationId((current) => current || records[0]?.id || "");
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
		void workspaceClient
			.jobs(organizationId)
			.then(setJobs)
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
					setNotice(
						job.safeError
							? `Processing failed: ${job.safeError}`
							: `Resume processing is ${job.status}.`,
					);
					if (job.status !== "ready" && job.status !== "processing") {
						setProcessingJobId(null);
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
		const interval = window.setInterval(poll, 3_000);
		return () => window.clearInterval(interval);
	}, [processingJobId]);

	if (isPending)
		return <main className="app-shell">Loading workspace...</main>;
	if (!session?.user)
		return <main className="app-shell">Sign in to use the workspace.</main>;

	const createOrganization = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		try {
			const organization =
				await workspaceClient.createOrganization(organizationName);
			setOrganizationName("");
			await loadOrganizations();
			setOrganizationId(organization.id);
			setNotice("Employer organization created.");
		} catch (reason) {
			reportError(reason);
		}
	};

	const createJob = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
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
			await loadJobs(organizationId);
			setNotice(
				"Job created. Confirm the requirements before uploading resumes.",
			);
		} catch (reason) {
			reportError(reason);
		}
	};

	const openJob = async (job: Job) => {
		try {
			const detail = await workspaceClient.job(job.id);
			setSelectedJob(detail);
			setEvaluations(await workspaceClient.evaluations(job.id));
			setOpenEvaluationId(null);
			setRequirements(
				detail.requirements.length
					? detail.requirements.map((requirement) => ({
							...requirement,
							normalizedText: requirement.text,
						}))
					: draftsToRequirements(detail),
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
			setSelectedJob(await workspaceClient.job(selectedJob.id));
			await loadJobs(organizationId);
			setNotice(
				"Requirements confirmed. Resume submissions are ready to process.",
			);
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
			setEvaluations(await workspaceClient.evaluations(selectedJob.id));
			setNotice(
				`Resume queued for processing: ${result.processingJobId}`,
			);
		} catch (reason) {
			reportError(reason);
		}
	};

	return (
		<main className="workspace-shell">
			<header className="workspace-header">
				<div className="brand-mark"><span>rs</span><span className="brand-name">resume screener</span></div>
				<nav className="workspace-nav" aria-label="Workspace navigation">
					<a className="active" href="#overview">Overview</a>
					<a href="#jobs">Jobs</a>
					<a href="#activity">Activity</a>
				</nav>
				<div className="user-menu"><span className="user-avatar">{session.user.name?.slice(0, 1).toUpperCase()}</span><span>{session.user.name}</span><Button variant="outline" onClick={() => authClient.signOut()}>Sign out</Button></div>
			</header>
			{error && <p className="form-error">{error}</p>}
			{notice && <p className="workspace-notice">{notice}</p>}
			<section className="workspace-intro" id="overview">
				<div><p className="eyebrow">Friday, 21 August 2026</p><h1>Good work starts with clear criteria.</h1><p className="intro-copy">Create a job, confirm what matters, and review the evidence behind every evaluation.</p></div>
				<div className="usage-meter"><div><span>Evaluation points</span><strong>240 <small>available</small></strong></div><div className="meter"><span /></div><p>60 points used this month</p></div>
			</section>
			<section className="metric-strip" aria-label="Workspace summary">
				<div><span>Active jobs</span><strong>{jobs.length}</strong><small>in your workspace</small></div>
				<div><span>Evaluations</span><strong>{evaluations.length}</strong><small>for selected job</small></div>
				<div><span>Top match</span><strong>{evaluations.find((evaluation) => evaluation.score !== null)?.score ?? "—"}<em>{evaluations.length ? "/100" : ""}</em></strong><small>best documented fit</small></div>
				<div><span>Weekly allowance</span><strong>1 <em>free</em></strong><small>renews Monday</small></div>
			</section>
			<section className="workspace-grid">
				<div className="workspace-column" id="jobs">
					<div className="section-heading"><div><p className="section-kicker">Your workspace</p><h2>Employer organizations</h2></div><span className="count-badge">{organizations.length}</span></div>
					<form className="inline-form" onSubmit={createOrganization}>
						<Input
							value={organizationName}
							onChange={(event) =>
								setOrganizationName(event.currentTarget.value)
							}
							placeholder="Organization name"
							required
						/>
						<Button type="submit">Create</Button>
					</form>
					<div className="selection-list">
						{organizations.map((organization) => (
							<button
								className={
									organization.id === organizationId
										? "selected"
										: ""
								}
								key={organization.id}
								onClick={() =>
									setOrganizationId(organization.id)
								}
								type="button"
							>
								{organization.name}
								<span>{organization.role}</span>
							</button>
						))}
					</div>
				</div>
				<div className="workspace-column">
					<div className="section-heading"><div><p className="section-kicker">Build a role</p><h2>Create a job</h2></div></div>
					<form className="stack-form" onSubmit={createJob}>
						<Label htmlFor="job-title">Title</Label>
						<Input
							id="job-title"
							value={jobTitle}
							onChange={(event) =>
								setJobTitle(event.currentTarget.value)
							}
							required
						/>
						<Label htmlFor="description">Job description</Label>
						<textarea
							id="description"
							value={description}
							onChange={(event) =>
								setDescription(event.currentTarget.value)
							}
							required
						/>
						<Button disabled={!organizationId} type="submit">
							Create job
						</Button>
					</form>
					<div className="section-heading jobs-heading"><div><p className="section-kicker">Recent roles</p><h2>Jobs</h2></div><span className="count-badge">{jobs.length}</span></div>
					<div className="selection-list">
						{jobs.map((job) => (
							<button
								key={job.id}
								onClick={() => void openJob(job)}
								type="button"
							>
								{job.title}
								<span>
									{job.confirmed
										? "Requirements confirmed"
										: "Needs confirmation"}
								</span>
							</button>
						))}
					</div>
				</div>
				<div className="workspace-column workspace-column-detail" id="activity">
					<div className="section-heading"><div><p className="section-kicker">Review with confidence</p><h2>Requirements and submissions</h2></div></div>
					{selectedJob ? (
						<>
							<p className="muted-copy">{selectedJob.title}</p>
							<div className="requirements-list">
								{requirements.map((requirement, index) => (
									<div key={requirement.stableId}>
										<Input
											value={
												requirement.normalizedText ?? ""
											}
											onChange={(event) =>
												setRequirements((current) =>
													current.map(
														(item, itemIndex) =>
															itemIndex === index
																? {
																		...item,
																		normalizedText:
																			event
																				.currentTarget
																				.value,
																	}
																: item,
													),
												)
											}
										/>
										<select
											value={requirement.kind}
											onChange={(event) =>
												setRequirements((current) =>
													current.map(
														(item, itemIndex) =>
															itemIndex === index
																? {
																		...item,
																		kind: event
																			.currentTarget
																			.value as Requirement["kind"],
																	}
																: item,
													),
												)
											}
										>
											<option value="required">
												Required
											</option>
											<option value="preferred">
												Preferred
											</option>
											<option value="hard_gate">
												Hard gate
											</option>
											<option value="ignored">
												Ignored
											</option>
										</select>
									</div>
								))}
							</div>
							<Button
								disabled={requirements.length === 0}
								onClick={() => void confirm()}
							>
								Confirm requirements
							</Button>
							{selectedJob.confirmed && (
								<form
									className="stack-form upload-form"
									onSubmit={upload}
								>
									<Label htmlFor="candidate-name">
										Candidate name
									</Label>
									<Input
										id="candidate-name"
										value={candidateName}
										onChange={(event) =>
											setCandidateName(
												event.currentTarget.value,
											)
										}
									/>
									<Label htmlFor="resume">Resume</Label>
									<Input
										accept=".pdf,.docx,.txt"
										id="resume"
										onChange={(event) =>
											setResume(
												event.currentTarget
													.files?.[0] ?? null,
											)
										}
										type="file"
										required
									/>
									<Button type="submit">Queue resume</Button>
								</form>
							)}
							{evaluations.length > 0 && (
								<div className="evaluation-list">
									<h3>Results</h3>
									{evaluations.map((evaluation) => (
										<div key={evaluation.id}>
											<button
												onClick={() =>
													setOpenEvaluationId(
														(current) =>
															current ===
															evaluation.id
																? null
																: evaluation.id,
													)
												}
												type="button"
											>
												<strong>
													{evaluation.candidateName ??
														"Candidate"}
												</strong>
												<span>
													{evaluation.score ??
														"Pending"}{" "}
													· {evaluation.eligibility}
												</span>
											</button>
											{openEvaluationId ===
												evaluation.id && (
												<div className="assessment-list">
													{evaluation.assessments.map(
														(assessment) => (
															<div
																key={
																	assessment.requirement
																}
															>
																<strong>
																	{
																		assessment.requirement
																	}
																</strong>
																<span>
																	{
																		assessment.outcome
																	}
																</span>
																<p>
																	{
																		assessment.reasoning
																	}
																</p>
																{assessment.evidence.map(
																	(
																		evidence,
																	) => (
																		<blockquote
																			key={
																				evidence.blockId
																			}
																		>
																			{
																				evidence.quote
																			}
																		</blockquote>
																	),
																)}
															</div>
														),
													)}
												</div>
											)}
										</div>
									))}
								</div>
							)}
						</>
					) : (
						<p className="muted-copy">
							Create or select a job to confirm its criteria.
						</p>
					)}
				</div>
			</section>
		</main>
	);

	function reportError(reason: unknown) {
		setNotice(null);
		setError(reason instanceof Error ? reason.message : "Request failed");
	}
};
