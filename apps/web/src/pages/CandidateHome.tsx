import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { Textarea } from "@resume-screener/ui/components/textarea";
import { FileSearch } from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import {
	candidateClient,
	type IndependentEvaluation,
} from "../features/candidate/client";
import { authClient } from "../lib/auth-client";

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
		if (
			!privateEvaluation ||
			["complete", "failed"].includes(privateEvaluation.status)
		)
			return;
		const interval = window.setInterval(async () => {
			const result = await candidateClient.independentEvaluation(
				privateEvaluation.id,
			);
			setPrivateEvaluation(result);
			if (["complete", "failed"].includes(result.status))
				void loadPrivateHistory();
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
									<FileSearch />
									{isWorking ? "Starting..." : "Check resume"}
								</Button>
							</form>
						)}
						{error && <p className="form-error">{error}</p>}
						{privateHistory.length > 0 && !privateEvaluation && (
							<div className="private-history">
								<h3>Previous checks</h3>
								{privateHistory.map((evaluation) => (
									<Button
										key={evaluation.id}
										onClick={() =>
											void openPrivateEvaluation(
												evaluation.id,
											)
										}
										size="sm"
										variant="outline"
									>
										{evaluation.originalName} ·{" "}
										{evaluation.status}
									</Button>
								))}
							</div>
						)}
					</section>
				</div>
			</section>
		</main>
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

const PrivateReport = ({
	evaluation,
	onClose,
}: {
	evaluation: IndependentEvaluation;
	onClose: () => void;
}) => {
	if (evaluation.status === "failed") {
		return (
			<p className="form-error">
				{evaluation.safeError ?? "This resume could not be processed."}
			</p>
		);
	}
	if (evaluation.status !== "complete") {
		return (
			<p>
				Checking your resume. This page updates when your private report
				is ready.
			</p>
		);
	}
	return (
		<div className="private-report">
			<p className="eyebrow">Private report</p>
			<h3>{evaluation.score}/100 document readiness</h3>
			<p>
				This indication reflects documented contact details and
				recognizable skills. It does not infer missing experience.
			</p>
			{evaluation.facts?.skills?.length ? (
				<div className="recognized-skills">
					<h4>Recognized skills</h4>
					{groupByCategory(evaluation.facts.skills).map(
						([category, names]) => (
							<p key={category}>
								<strong>{category}</strong> {names.join(", ")}
							</p>
						),
					)}
				</div>
			) : null}
			{evaluation.suggestions?.map((suggestion) => (
				<p key={suggestion.title}>
					<strong>{suggestion.title}</strong>
					<br />
					{suggestion.detail}
				</p>
			))}
			<Button onClick={onClose} size="sm" variant="outline">
				Check another resume
			</Button>
		</div>
	);
};
