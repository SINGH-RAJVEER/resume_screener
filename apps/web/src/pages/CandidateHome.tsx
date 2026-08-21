import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { Textarea } from "@resume-screener/ui/components/textarea";
import {
	ArrowRight,
	CheckCircle2,
	FileSearch,
	Link2,
	UploadCloud,
} from "lucide-react";
import { type FormEvent, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import {
	candidateClient,
	type IndependentEvaluation,
} from "../features/candidate/client";
import { authClient } from "../lib/auth-client";

const tokenFromValue = (value: string) => {
	const trimmed = value.trim();
	try {
		const url = new URL(trimmed);
		return url.searchParams.get("invitation") ?? trimmed;
	} catch {
		return trimmed;
	}
};

export const CandidateHome = () => {
	const { data: session } = authClient.useSession();
	const [searchParams] = useSearchParams();
	const [invitationValue, setInvitationValue] = useState(
		searchParams.get("invitation") ?? "",
	);
	const [activeToken, setActiveToken] = useState<string | null>(null);
	const [jobId, setJobId] = useState<string | null>(null);
	const [resume, setResume] = useState<File | null>(null);
	const [isWorking, setIsWorking] = useState(false);
	const [submitted, setSubmitted] = useState(false);
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

	const redeem = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const token = tokenFromValue(invitationValue);
		if (!token) return;
		setError(null);
		setIsWorking(true);
		try {
			const result = /^[A-Za-z0-9]{8}$/.test(token)
				? await candidateClient.redeemPasscode(token)
				: await candidateClient.redeemInvitation(token);
			setActiveToken(token);
			setJobId(result.jobId);
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "Invitation could not be opened",
			);
		} finally {
			setIsWorking(false);
		}
	};

	const upload = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!activeToken || !jobId || !resume) return;
		setError(null);
		setIsWorking(true);
		try {
			await candidateClient.uploadInvitedResume(
				jobId,
				activeToken,
				resume,
				session?.user.name ?? "",
			);
			setSubmitted(true);
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "Resume upload failed",
			);
		} finally {
			setIsWorking(false);
		}
	};

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
						Submit a resume through an employer invitation.
						Employers only receive the document you deliberately
						submit.
					</p>
				</header>

				<div className="candidate-grid">
					<section className="candidate-action">
						<div className="candidate-action-heading">
							<Link2 />
							<div>
								<h2>Employer invitation</h2>
								<p>Use the link sent by the employer.</p>
							</div>
						</div>
						{submitted ? (
							<div className="submission-success">
								<CheckCircle2 />
								<h3>Resume submitted</h3>
								<p>
									Your document was received and queued for
									processing. Evaluation results remain
									private to the employer.
								</p>
							</div>
						) : jobId && activeToken ? (
							<form className="candidate-form" onSubmit={upload}>
								<div className="form-field">
									<Label htmlFor="invited-resume">
										Resume document
									</Label>
									<Input
										accept=".pdf,.docx,.txt"
										id="invited-resume"
										onChange={(event) =>
											setResume(
												event.currentTarget
													.files?.[0] ?? null,
											)
										}
										required
										type="file"
									/>
									<p className="form-hint">
										PDF, DOCX, or TXT. Maximum 20 MB.
										Scanned PDFs are not supported.
									</p>
								</div>
								<Button
									disabled={!resume || isWorking}
									type="submit"
								>
									<UploadCloud />
									{isWorking
										? "Uploading..."
										: "Submit resume"}
								</Button>
							</form>
						) : (
							<form className="candidate-form" onSubmit={redeem}>
								<div className="form-field">
									<Label htmlFor="invitation">
										Invitation link or passcode
									</Label>
									<Input
										id="invitation"
										onChange={(event) =>
											setInvitationValue(
												event.currentTarget.value,
											)
										}
										placeholder="Paste a link or enter an 8-character passcode"
										required
										value={invitationValue}
									/>
								</div>
								<Button disabled={isWorking} type="submit">
									{isWorking
										? "Opening invitation..."
										: "Continue"}
									<ArrowRight />
								</Button>
							</form>
						)}
						{error && (
							<p className="form-error" role="alert">
								{error}
							</p>
						)}
					</section>

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
				<p>
					Recognized skills:{" "}
					{evaluation.facts.skills
						.map((skill) => skill.canonicalName)
						.join(", ")}
				</p>
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
