import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { Textarea } from "@skillsignal/ui/components/textarea";
import { AlertTriangle, FileDown, FileSearch, Trash2 } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";
import {
	candidateClient,
	type EmploymentFact,
	type IndependentEvaluation,
} from "./client";

const PROCESSING_STEPS = [
	"Reading the document",
	"Checking documented facts",
	"Preparing the private report",
];

const isPendingStatus = (status: IndependentEvaluation["status"]) =>
	status === "queued" || status === "processing";

export const PrivateEvaluationWorkspace = () => {
	const [isWorking, setIsWorking] = useState(false);
	const [isLoadingHistory, setIsLoadingHistory] = useState(true);
	const [error, setError] = useState<string | null>(null);
	const [historyError, setHistoryError] = useState<string | null>(null);
	const [privateResume, setPrivateResume] = useState<File | null>(null);
	const [jobDescription, setJobDescription] = useState("");
	const [jobDescriptionFile, setJobDescriptionFile] = useState<File | null>(
		null,
	);
	const [fileInputKey, setFileInputKey] = useState(0);
	const [privateEvaluation, setPrivateEvaluation] =
		useState<IndependentEvaluation | null>(null);
	const [privateHistory, setPrivateHistory] = useState<
		IndependentEvaluation[]
	>([]);
	const [confirmDeleteId, setConfirmDeleteId] = useState<string | null>(null);
	const [deletingId, setDeletingId] = useState<string | null>(null);
	const historyIsUnavailable =
		historyError !== null && privateHistory.length === 0;

	const loadPrivateHistory = useCallback(async () => {
		setHistoryError(null);
		try {
			setPrivateHistory(await candidateClient.independentEvaluations());
		} catch {
			setHistoryError("Previous checks could not be loaded.");
		} finally {
			setIsLoadingHistory(false);
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
				jobDescriptionFile,
			);
			setPrivateEvaluation({
				id: result.id,
				originalName: privateResume.name,
				status: "queued",
				score: null,
				safeError: null,
				jobDescriptionProvided: Boolean(
					jobDescription.trim() || jobDescriptionFile,
				),
				createdAt: new Date().toISOString(),
				completedAt: null,
			});
			setPrivateResume(null);
			setJobDescription("");
			setJobDescriptionFile(null);
			setFileInputKey((key) => key + 1);
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

	const deleteEvaluation = async (evaluationId: string) => {
		setDeletingId(evaluationId);
		setHistoryError(null);
		try {
			await candidateClient.deleteIndependentEvaluation(evaluationId);
			setPrivateHistory((history) =>
				history.filter((evaluation) => evaluation.id !== evaluationId),
			);
			if (privateEvaluation?.id === evaluationId)
				setPrivateEvaluation(null);
			setConfirmDeleteId(null);
		} catch (reason) {
			setHistoryError(
				reason instanceof Error
					? reason.message
					: "The report could not be deleted.",
			);
		} finally {
			setDeletingId(null);
		}
	};

	return (
		<div className="candidate-workspace">
			<section
				className="candidate-primary"
				aria-labelledby="private-check-title"
			>
				<header className="candidate-action-heading">
					<FileSearch aria-hidden />
					<div>
						<h2 id="private-check-title">Private resume check</h2>
						<p>
							Add a job description only when you want
							role-specific guidance.
						</p>
					</div>
				</header>

				{privateEvaluation ? (
					<PrivateReport
						evaluation={privateEvaluation}
						onClose={() => setPrivateEvaluation(null)}
					/>
				) : (
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
								key={`resume-${fileInputKey}`}
								onChange={(event) =>
									setPrivateResume(
										event.currentTarget.files?.[0] ?? null,
									)
								}
								required
								type="file"
							/>
							<p className="form-hint">
								PDF, DOCX, or TXT. Maximum 20 MB.
							</p>
						</div>
						<div className="form-field">
							<Label htmlFor="job-description">
								Job description, optional
							</Label>
							<Textarea
								disabled={Boolean(jobDescriptionFile)}
								id="job-description"
								onChange={(event) =>
									setJobDescription(event.currentTarget.value)
								}
								placeholder="Paste the role description"
								value={jobDescription}
							/>
							<div className="candidate-file-alternative">
								<span>or upload it</span>
								<Input
									accept=".pdf,.docx,.txt"
									id="job-description-file"
									key={`job-${fileInputKey}`}
									onChange={(event) => {
										const selected =
											event.currentTarget.files?.[0] ??
											null;
										setJobDescriptionFile(selected);
										if (selected) setJobDescription("");
									}}
									type="file"
								/>
							</div>
						</div>
						<Button
							disabled={!privateResume || isWorking}
							type="submit"
						>
							{isWorking ? (
								<ThinkingOrb
									aria-hidden
									size={20}
									state="solving"
								/>
							) : (
								<FileSearch aria-hidden />
							)}
							{isWorking ? "Starting check" : "Check resume"}
						</Button>
					</form>
				)}
				{error && (
					<p className="form-error" role="alert">
						{error}
					</p>
				)}
			</section>

			<aside
				className="candidate-history"
				aria-labelledby="history-title"
			>
				<header>
					<p className="eyebrow">Private archive</p>
					<h2 id="history-title">Previous checks</h2>
				</header>
				{historyError && (
					<div className="candidate-empty" role="alert">
						<p>{historyError}</p>
						{privateHistory.length === 0 && (
							<Button
								onClick={() => void loadPrivateHistory()}
								size="sm"
								variant="outline"
							>
								Try again
							</Button>
						)}
					</div>
				)}
				{isLoadingHistory ? (
					<p className="candidate-empty">Loading your checks...</p>
				) : historyIsUnavailable ? null : privateHistory.length ===
					0 ? (
					<p className="candidate-empty">
						Completed and in-progress checks will appear here.
					</p>
				) : (
					<ul className="candidate-history-list">
						{privateHistory.map((evaluation) => (
							<li
								data-active={
									privateEvaluation?.id === evaluation.id
								}
								key={evaluation.id}
							>
								{confirmDeleteId === evaluation.id ? (
									<div className="history-confirm-delete">
										<p>Delete this report and its files?</p>
										<div className="history-confirm-actions">
											<Button
												disabled={
													deletingId === evaluation.id
												}
												onClick={() =>
													void deleteEvaluation(
														evaluation.id,
													)
												}
												size="xs"
												variant="destructive"
											>
												{deletingId === evaluation.id
													? "Deleting"
													: "Delete"}
											</Button>
											<Button
												onClick={() =>
													setConfirmDeleteId(null)
												}
												size="xs"
												variant="ghost"
											>
												Keep it
											</Button>
										</div>
									</div>
								) : (
									<>
										<button
											className="history-open"
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
											{evaluation.jobDescriptionProvided && (
												<small>
													Job description included
												</small>
											)}
										</button>
										<Button
											aria-label={`Delete ${evaluation.originalName}`}
											onClick={() =>
												setConfirmDeleteId(
													evaluation.id,
												)
											}
											size="icon-xs"
											variant="ghost"
										>
											<Trash2 aria-hidden />
										</Button>
									</>
								)}
							</li>
						))}
					</ul>
				)}
			</aside>
		</div>
	);
};

const ProcessingState = () => {
	const [stepIndex, setStepIndex] = useState(0);

	useEffect(() => {
		if (stepIndex >= PROCESSING_STEPS.length - 1) return;
		const timeout = window.setTimeout(() => {
			setStepIndex((index) => index + 1);
		}, 1_800);
		return () => window.clearTimeout(timeout);
	}, [stepIndex]);

	return (
		<div className="report-progress" role="status" aria-live="polite">
			<div className="report-progress-heading">
				<ThinkingOrb aria-hidden size={20} state="solving" />
				<div>
					<strong>Your private report is in progress</strong>
					<p>{PROCESSING_STEPS[stepIndex]}</p>
				</div>
			</div>
			<ol>
				{PROCESSING_STEPS.map((step, index) => (
					<li data-active={index === stepIndex} key={step}>
						{step}
					</li>
				))}
			</ol>
			<small>
				You can leave this page and reopen the report from your private
				archive.
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
	const title = [role.title, role.employer].filter(Boolean).join(" at ");
	const end = role.isCurrent ? "present" : role.endDate;
	const dates = [role.startDate, end].filter(Boolean).join(" to ");
	return dates ? `${title}, ${dates}` : title;
};

const readinessLabel = (score: number | null) => {
	if (score === null) return "Not enough documented information";
	if (score >= 80) return "Strong document coverage";
	if (score >= 60) return "Useful foundation, with gaps";
	return "Important sections need attention";
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
			<div className="private-report report-failure">
				<AlertTriangle aria-hidden />
				<h3>This document could not be checked</h3>
				<p>
					{evaluation.safeError ??
						"Upload a digital PDF, DOCX, or TXT file."}
				</p>
				<Button onClick={onClose} size="sm" variant="outline">
					Try another document
				</Button>
			</div>
		);
	}
	if (isPendingStatus(evaluation.status)) return <ProcessingState />;

	const facts = evaluation.facts ?? {};
	const skillGroups = groupByCategory(facts.skills ?? []);
	const warnings = facts.warnings ?? [];

	return (
		<article className="private-report report-preview">
			<header>
				<div>
					<span>{evaluation.originalName}</span>
					{evaluation.jobDescriptionProvided && (
						<b className="report-context">Role guidance included</b>
					)}
				</div>
				<span>
					{evaluation.completedAt
						? new Date(evaluation.completedAt).toLocaleDateString()
						: null}
				</span>
			</header>
			<section className="report-score" aria-label="Resume readiness">
				<strong>{evaluation.score ?? "–"}</strong>
				<span>of 100 resume readiness</span>
				<b>{readinessLabel(evaluation.score)}</b>
				<p>
					The score describes this document, not your ability. Missing
					evidence is not treated as a proven lack of experience.
				</p>
			</section>

			{warnings.length > 0 && (
				<section className="report-section report-warnings">
					<h4>Document warnings</h4>
					<ul>
						{warnings.map((warning) => (
							<li key={warning}>{warning}</li>
						))}
					</ul>
				</section>
			)}

			{skillGroups.length > 0 && (
				<section className="report-section">
					<h4>Documented skills</h4>
					{skillGroups.map(([category, names]) => (
						<p key={category}>
							<strong>{category}</strong> {names.join(", ")}
						</p>
					))}
				</section>
			)}

			{(facts.employment?.length ?? 0) > 0 && (
				<section className="report-section">
					<h4>Documented experience</h4>
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
								.join(", ")}
						</p>
					))}
				</section>
			)}

			<section className="report-section report-suggestions">
				<h4>Changes to consider</h4>
				{(evaluation.suggestions?.length ?? 0) > 0 ? (
					evaluation.suggestions?.map((suggestion) => (
						<div
							className="suggestion-row"
							key={`${suggestion.title}-${suggestion.detail}`}
						>
							<b>{suggestion.title}</b>
							<p>{suggestion.detail}</p>
						</div>
					))
				) : (
					<p>No immediate document changes were identified.</p>
				)}
			</section>

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
						<FileDown aria-hidden />
						Download corrected resume
					</Button>
				)}
				<Button onClick={onClose} size="sm" variant="outline">
					Check another resume
				</Button>
				{downloadError && (
					<p className="form-error" role="alert">
						{downloadError}
					</p>
				)}
			</footer>
		</article>
	);
};
