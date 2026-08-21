import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { CheckCircle2, UploadCloud } from "lucide-react";
import { type ChangeEvent, type FormEvent, useEffect, useState } from "react";
import { Navigate, useParams } from "react-router-dom";
import { candidateClient } from "../features/candidate/client";
import { authClient } from "../lib/auth-client";

export const InvitationUpload = () => {
	const { token } = useParams();
	const { data: session, isPending } = authClient.useSession();
	const [jobId, setJobId] = useState<string | null>(null);
	const [resume, setResume] = useState<File | null>(null);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [submitted, setSubmitted] = useState(false);
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
			await candidateClient.uploadInvitedResume(
				jobId,
				token,
				resume,
				session.user.name,
			);
			setSubmitted(true);
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
		setResume(event.currentTarget.files?.[0] ?? null);
	};

	return (
		<main className="candidate-page">
			<header className="candidate-header">
				<div className="brand-mark">
					<span>rs</span>
					<span className="brand-name">resume screener</span>
				</div>
				<span>{session.user.name}</span>
			</header>
			<section className="candidate-content">
				<header className="candidate-intro">
					<p className="eyebrow">Job application</p>
					<h1>Submit your resume.</h1>
					<p>
						Only the employer who sent this link receives your
						submission.
					</p>
				</header>
				<section className="candidate-action">
					{submitted ? (
						<div className="submission-success">
							<CheckCircle2 />
							<h2>Resume submitted</h2>
							<p>
								Your document was received and queued for
								processing.
							</p>
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
								<UploadCloud />
								{isSubmitting
									? "Uploading..."
									: "Submit resume"}
							</Button>
						</form>
					) : (
						<p>Opening invitation...</p>
					)}
					{error && <p className="form-error">{error}</p>}
				</section>
			</section>
		</main>
	);
};
