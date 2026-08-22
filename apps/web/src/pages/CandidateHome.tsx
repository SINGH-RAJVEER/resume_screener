import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { Textarea } from "@resume-screener/ui/components/textarea";
import { FileDown, FileSearch, LoaderCircle } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
	candidateClient,
	type EmploymentFact,
	type IndependentEvaluation,
} from "../features/candidate/client";
import { authClient } from "../lib/auth-client";

const PROCESSING_STEPS = [
	"Reading your document",
	"Recognizing documented skills",
	"Checking contact details and sections",
	"Preparing suggestions",
];

const isPendingStatus = (status: IndependentEvaluation["status"]) =>
	status === "queued" || status === "processing";

export const CandidateHome = () => {
	const { data: session } = authClient.useSession();
	const [isWorking, setIsWorking] = useState(false);
	const [error, setError] = useState<string | null>(null);
	const [privateResume, setPrivateResume] = useState<File | null>(null);
	const [jobDescription, setJobDescription] = useState("");
	const [privateEvaluation, setPrivateEvaluation] =
		useState<IndependentEvaluation | null>(null);
	const [privateHistory, setPrivateHistory] = useState<
		IndependentEvaluation[]
	>([]);

	const loadPrivateHistory = useCallback(async () => {
		try {
			setPrivateHistory(await candidateClient.independentEvaluations());
		} catch {
			setPrivateHistory([]);
		}
	}, []);

	useEffect(() => {
		void loadPrivateHistory();
	}, [loadPrivateHistory]);

	useEffect(() => {
		if (!privateEvaluation || !isPendingStatus(privateEvaluation.status))
			return;
		const interval = window.setInterval(async () => {
			try {
				const result = await candidateClient.independentEvaluation(
					privateEvaluation.id,
				);
				setPrivateEvaluation(result);
				if (!isPendingStatus(result.status)) void loadPrivateHistory();
			} catch {
				setPrivateEvaluation(null);
				setError("Your report could not be loaded. Try again.");
			}
		}, 2_000);
		return () => window.clearInterval(interval);
	}, [loadPrivateHistory, privateEvaluation]);

	const startPrivateEvaluation = async (
		event: FormEvent<HTMLFormElement>,
	) => {
		event.preventDefault();
		if (!privateResume) return;
		setError(null);
		setIsWorking(true);
		try {
			const result = await candidateClient.createIndependentEvaluation(
				privateResume,
				jobDescription,
			);
			setPrivateEvaluation({
				id: result.id,
				originalName: privateResume.name,
				status: "queued",
				score: null,
				safeError: null,
				createdAt: new Date().toISOString(),
				completedAt: null,
			});
			setPrivateResume(null);
			setJobDescription("");
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "Resume check could not start",
			);
		} finally {
			setIsWorking(false);
		}
	};

	const openPrivateEvaluation = async (evaluationId: string) => {
		setError(null);
		setPrivateEvaluation(null);
		try {
			setPrivateEvaluation(
				await candidateClient.independentEvaluation(evaluationId),
			);
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "Report could not be opened",
			);
		}
	};

	return (
		<main className="candidate-page">
			<header className="candidate-header">
				<div className="brand-mark">
					<span>rs</span>
					<span className="brand-name">resume screener</span>
				</div>
				<div>
					<span>{session?.user.name}</span>
					<Button
						onClick={() => authClient.signOut()}
						size="sm"
						variant="outline"
					>
						Sign out
					</Button>
				</div>
			</header>

			<section className="candidate-content">
				<header className="candidate-intro">
					<p className="eyebrow">Candidate workspace</p>
					<h1>Your resume, under your control.</h1>
					<p>
						Run private checks without sharing your resume with an
						employer.
					</p>
				</header>

				<div className="candidate-grid">
					<section className="candidate-action">
						<div className="candidate-action-heading">
							<FileSearch />
							<div>
								<h2>Private resume check</h2>
								<p>
									Compare your resume with a job description.
								</p>
							</div>
						</div>
						{privateEvaluation ? (
							<PrivateReport
								evaluation={privateEvaluation}
								onClose={() => setPrivateEvaluation(null)}
							/>
						) : (
							<>
								<form
									className="candidate-form"
									onSubmit={startPrivateEvaluation}
								>
									<div className="form-field">
										<Label htmlFor="private-resume">
											Resume document
										</Label>
										<Input
											accept=".pdf,.docx,.txt"
											id="private-resume"
											onChange={(event) =>
												setPrivateResume(
													event.currentTarget
														.files?.[0] ?? null,
												)
											}
											required
											type="file"
										/>
										<p className="form-hint">
											PDF, DOCX, or TXT.
										</p>
									</div>
									<div className="form-field">
										<Label htmlFor="job-description">
											Job description (optional)
										</Label>
										<Textarea
											id="job-description"
											onChange={(event) =>
												setJobDescription(
													event.currentTarget.value,
												)
											}
											placeholder="Paste a role description to receive role-specific guidance."
											value={jobDescription}
										/>
									</div>
									<Button
										disabled={!privateResume || isWorking}
										type="submit"
									>
										{isWorking ? (
											<LoaderCircle
												aria-hidden
												className="spin"
											/>
										) : (
											<FileSearch />
										)}
										{isWorking
											? "Starting..."
											: "Check resume"}
									</Button>
								</form>
								{error && <p className="form-error">{error}</p>}
								{privateHistory.length > 0 && (
									<div className="private-history">
										<h3>Previous checks</h3>
										{privateHistory.map((evaluation) => (
											<button
												key={evaluation.id}
												onClick={() =>
													void openPrivateEvaluation(
														evaluation.id,
													)
												}
												type="button"
											>
												<span className="history-name">
													{evaluation.originalName}
												</span>
												<span className="history-meta">
													{evaluation.score !== null
														? `${evaluation.score}/100`
														: evaluation.status}
													{" · "}
													{new Date(
														evaluation.createdAt,
													).toLocaleDateString()}
												</span>
											</button>
										))}
									</div>
								)}
							</>
						)}
					</section>
				</div>
			</section>
		</main>
	);
};

const ProcessingState = () => {
	const [stepIndex, setStepIndex] = useState(0);

	useEffect(() => {
		const interval = window.setInterval(() => {
			setStepIndex((index) => index + 1);
		}, 1_800);
		return () => window.clearInterval(interval);
	}, []);

	return (
		<div className="report-progress" role="status" aria-live="polite">
			<LoaderCircle aria-hidden className="spin" />
			<p>{PROCESSING_STEPS[stepIndex % PROCESSING_STEPS.length]}</p>
			<small>
				This usually takes under a minute. Your document stays private.
			</small>
		</div>
	);
};

const groupByCategory = (
	skills: Array<{ canonicalName: string; category?: string | null }>,
): Array<[string, string[]]> => {
	const grouped = new Map<string, string[]>();
	for (const skill of skills) {
		const category = skill.category ?? "Other";
		grouped.set(category, [
			...(grouped.get(category) ?? []),
			skill.canonicalName,
		]);
	}
	return [...grouped.entries()].sort(([a], [b]) => a.localeCompare(b));
};

const employmentLine = (role: EmploymentFact) => {
	const title = [role.title, role.employer].filter(Boolean).join(" — ");
	const end = role.isCurrent ? "present" : role.endDate;
	const dates = [role.startDate, end].filter(Boolean).join(" to ");
	return dates ? `${title} (${dates})` : title;
};

const PrivateReport = ({
	evaluation,
	onClose,
}: {
	evaluation: IndependentEvaluation;
	onClose: () => void;
}) => {
	const [downloadError, setDownloadError] = useState<string | null>(null);

	if (evaluation.status === "failed") {
		return (
			<div className="private-report">
				<p className="form-error">
					{evaluation.safeError ??
						"This resume could not be processed."}
				</p>
				<Button onClick={onClose} size="sm" variant="outline">
					Try another document
				</Button>
			</div>
		);
	}
	if (isPendingStatus(evaluation.status)) {
		return <ProcessingState />;
	}

	const facts = evaluation.facts ?? {};
	const skillGroups = groupByCategory(facts.skills ?? []);

	return (
		<div className="private-report report-preview">
			<header>
				<span>{evaluation.originalName}</span>
				<span>
					{evaluation.completedAt
						? new Date(evaluation.completedAt).toLocaleDateString()
						: null}
				</span>
			</header>
			<div className="report-score">
				<strong>{evaluation.score ?? "–"}</strong>
				<span>of 100 readiness</span>
				<p>
					Based only on what your resume documents. It does not infer
					missing experience.
				</p>
			</div>

			{skillGroups.length > 0 && (
				<section className="report-section">
					<h4>Recognized skills</h4>
					{skillGroups.map(([category, names]) => (
						<p key={category}>
							<strong>{category}</strong> {names.join(", ")}
						</p>
					))}
				</section>
			)}

			{(facts.employment?.length ?? 0) > 0 && (
				<section className="report-section">
					<h4>Experience</h4>
					{facts.employment?.map((role) => (
						<p
							key={`${role.title}-${role.employer}-${role.startDate}`}
						>
							{employmentLine(role)}
						</p>
					))}
				</section>
			)}

			{((facts.education?.length ?? 0) > 0 ||
				(facts.certifications?.length ?? 0) > 0) && (
				<section className="report-section">
					<h4>Education and credentials</h4>
					{facts.education?.map((entry) => (
						<p
							key={`${entry.degree}-${entry.institution}-${entry.graduationDate}`}
						>
							{[
								entry.degree,
								entry.fieldOfStudy,
								entry.institution,
							]
								.filter(Boolean)
								.join(", ")}
						</p>
					))}
					{facts.certifications?.map((entry) => (
						<p key={`${entry.name}-${entry.issuer}`}>
							{[entry.name, entry.issuer]
								.filter(Boolean)
								.join(" — ")}
						</p>
					))}
				</section>
			)}

			{(evaluation.suggestions?.length ?? 0) > 0 && (
				<section className="report-section">
					<h4>Suggestions</h4>
					{evaluation.suggestions?.map((suggestion) => (
						<div className="suggestion-row" key={suggestion.title}>
							<b>{suggestion.title}</b>
							<p>{suggestion.detail}</p>
						</div>
					))}
				</section>
			)}

			<footer className="report-actions">
				{evaluation.hasImprovedResume && (
					<Button
						onClick={() => {
							setDownloadError(null);
							candidateClient
								.downloadImprovedResume(evaluation.id)
								.catch(() =>
									setDownloadError(
										"The corrected resume could not be downloaded. Try again.",
									),
								);
						}}
						size="sm"
					>
						<FileDown />
						Corrected resume (.docx)
					</Button>
				)}
				<Button onClick={onClose} size="sm" variant="outline">
					{evaluation.hasImprovedResume
						? "Check another resume"
						: "Check another"}
				</Button>
				{downloadError && <p className="form-error">{downloadError}</p>}
			</footer>
		</div>
	);
};
