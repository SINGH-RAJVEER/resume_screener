import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { CheckCircle2, UploadCloud } from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { Link, Navigate, useParams } from "react-router-dom";
import { candidateClient } from "../features/candidate/client";
import { authClient } from "../lib/auth-client";

export const InvitationUpload = () => {
	const { token } = useParams();
	const { data: session, isPending } = authClient.useSession();
	const [jobId, setJobId] = useState<string | null>(null);
	const [resume, setResume] = useState<File | null>(null);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [receipt, setReceipt] = useState<{
		submissionId: string;
		receivedAt: Date;
	} | null>(null);
	const [error, setError] = useState<string | null>(null);

	useEffect(() => {
		if (!token || !session || session.user.accountType !== "candidate")
			return;
		let cancelled = false;
		void candidateClient
			.redeemInvitation(token)
			.then((result) => {
				if (!cancelled) setJobId(result.jobId);
			})
			.catch((reason: unknown) => {
				if (!cancelled)
					setError(
						reason instanceof Error
							? reason.message
							: "This invitation is unavailable.",
					);
			});
		return () => {
			cancelled = true;
		};
	}, [session, token]);

	if (isPending) return <main className="app-shell">Loading...</main>;
	if (!token) return <Navigate replace to="/" />;
	if (!session) {
		const returnTo = encodeURIComponent(`/apply/${token}`);
		return (
			<Navigate
				replace
				to={`/sign-up?mode=invited&returnTo=${returnTo}`}
			/>
		);
	}
	if (session.user.accountType !== "candidate") {
		return (
			<main className="auth-page">
				<section className="auth-panel">
					<h1>Candidate account required</h1>
					<p>
						Sign out, then create or sign in to a candidate account
						to submit this resume.
					</p>
					<Button onClick={() => authClient.signOut()}>
						Sign out
					</Button>
				</section>
			</main>
		);
	}

	const upload = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!jobId || !resume) return;
		setError(null);
		setIsSubmitting(true);
		try {
			const result = await candidateClient.uploadInvitedResume(
				jobId,
				token,
				resume,
			);
			setReceipt({
				submissionId: result.submissionId,
				receivedAt: new Date(),
			});
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "Resume upload failed.",
			);
		} finally {
			setIsSubmitting(false);
		}
	};

	const selectResume = (event: ChangeEvent<HTMLInputElement>) => {
		setError(null);
		setResume(event.currentTarget.files?.[0] ?? null);
	};

	return (
		<main className="candidate-page">
			<header className="candidate-header">
				<div className="brand-mark">
					<img src="/icon.webp" alt="SkillSignal" />
				</div>
				<span>{session.user.name}</span>
			</header>
			<section className="candidate-content">
				<header className="candidate-intro">
					<p className="eyebrow">Employer submission</p>
					<h1>Submit your resume.</h1>
					<p>
						Only the employer who sent this link receives your
						submission.
					</p>
				</header>
				<section className="candidate-action">
					{receipt ? (
						<div className="submission-success" role="status">
							<CheckCircle2 aria-hidden />
							<p className="eyebrow">Submission received</p>
							<h2>The employer has your resume.</h2>
							<p>
								Received {receipt.receivedAt.toLocaleString()}.
								The document is queued for processing.
							</p>
							<code>{receipt.submissionId}</code>
							<p>
								This page does not show the employer's score,
								eligibility result, or review decision.
							</p>
							<Button asChild size="sm" variant="outline">
								<Link to="/">Go to private resume checks</Link>
							</Button>
						</div>
					) : jobId ? (
						<form className="candidate-form" onSubmit={upload}>
							<div className="form-field">
								<Label htmlFor="invited-resume">
									Resume document
								</Label>
								<Input
									accept=".pdf,.docx,.txt"
									id="invited-resume"
									onChange={selectResume}
									required
									type="file"
								/>
								<p className="form-hint">
									PDF, DOCX, or TXT. Maximum 20 MB.
								</p>
							</div>
							<Button
								disabled={!resume || isSubmitting}
								type="submit"
							>
								<UploadCloud aria-hidden />
								{isSubmitting ? "Uploading" : "Submit resume"}
							</Button>
						</form>
					) : error ? null : (
						<p role="status">Opening invitation...</p>
					)}
					{error && (
						<p className="form-error" role="alert">
							{error}
						</p>
					)}
				</section>
			</section>
		</main>
	);
};
