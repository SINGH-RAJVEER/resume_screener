import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { type FormEvent, useEffect, useState } from "react";
import { authClient } from "../lib/auth-client";
import {
	type Job,
	type JobDetail,
	type Organization,
	type Requirement,
	workspaceClient,
} from "../lib/workspace-client";

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
				<div>
					<p className="eyebrow">Resume screener</p>
					<h1>Employer workspace</h1>
				</div>
				<Button variant="outline" onClick={() => authClient.signOut()}>
					Sign out
				</Button>
			</header>
			{error && <p className="form-error">{error}</p>}
			{notice && <p className="workspace-notice">{notice}</p>}
			<section className="workspace-grid">
				<div className="workspace-column">
					<h2>Employer organizations</h2>
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
					<h2>Create a job</h2>
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
					<h2>Jobs</h2>
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
				<div className="workspace-column">
					<h2>Requirements and submissions</h2>
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
