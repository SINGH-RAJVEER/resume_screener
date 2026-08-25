import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { CheckCircle2, KeyRound, UploadCloud } from "lucide-react";
import { type FormEvent, useState } from "react";
import { ThinkingOrb } from "thinking-orbs";
import { candidateClient } from "./client";

type RedeemedInvitation = {
	jobId: string;
	passcode: string;
};

type SubmissionReceipt = {
	submissionId: string;
	receivedAt: Date;
};

export const CandidateSubmissionWorkspace = () => {
	const [passcode, setPasscode] = useState("");
	const [invitation, setInvitation] = useState<RedeemedInvitation | null>(
		null,
	);
	const [resume, setResume] = useState<File | null>(null);
	const [receipt, setReceipt] = useState<SubmissionReceipt | null>(null);
	const [isRedeeming, setIsRedeeming] = useState(false);
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const redeem = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const normalized = passcode.trim().toUpperCase();
		if (!normalized) return;
		setError(null);
		setIsRedeeming(true);
		try {
			const result = await candidateClient.redeemPasscode(normalized);
			setInvitation({ jobId: result.jobId, passcode: normalized });
		} catch (reason) {
			setError(
				reason instanceof Error
					? reason.message
					: "This passcode is unavailable.",
			);
		} finally {
			setIsRedeeming(false);
		}
	};

	const submitResume = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!invitation || !resume) return;
		setError(null);
		setIsSubmitting(true);
		try {
			const result = await candidateClient.uploadInvitedResume(
				invitation.jobId,
				invitation.passcode,
				resume,
			);
			setReceipt({
				submissionId: result.submissionId,
				receivedAt: new Date(),
			});
			setResume(null);
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

	const startAgain = () => {
		setPasscode("");
		setInvitation(null);
		setReceipt(null);
		setResume(null);
		setError(null);
	};

	return (
		<section
			className="candidate-submission"
			aria-labelledby="submission-title"
		>
			<header className="candidate-action-heading">
				<KeyRound aria-hidden />
				<div>
					<h2 id="submission-title">Submit to an employer</h2>
					<p>
						Use the single-use passcode from the employer. You will
						not see their evaluation here.
					</p>
				</div>
			</header>

			{receipt ? (
				<div className="submission-receipt" role="status">
					<CheckCircle2 aria-hidden />
					<p className="eyebrow">Submission received</p>
					<h3>The employer has your resume.</h3>
					<p>
						Received {receipt.receivedAt.toLocaleString()}. Keep
						this reference if you need to identify the upload.
					</p>
					<code>{receipt.submissionId}</code>
					<p className="receipt-privacy">
						This receipt does not show the employer's evaluation,
						eligibility result, or review decision. SkillSignal will
						not send interview or rejection messages for the
						employer.
					</p>
					<Button onClick={startAgain} size="sm" variant="outline">
						Use another passcode
					</Button>
				</div>
			) : invitation ? (
				<form className="candidate-form" onSubmit={submitResume}>
					<div className="submission-passcode-confirmed">
						<CheckCircle2 aria-hidden />
						<span>Passcode accepted</span>
						<button onClick={startAgain} type="button">
							Use a different code
						</button>
					</div>
					<div className="form-field">
						<Label htmlFor="submission-resume">
							Resume document
						</Label>
						<Input
							accept=".pdf,.docx,.txt"
							id="submission-resume"
							onChange={(event) =>
								setResume(
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
					<Button disabled={!resume || isSubmitting} type="submit">
						{isSubmitting ? (
							<ThinkingOrb
								aria-hidden
								size={20}
								state="solving"
							/>
						) : (
							<UploadCloud aria-hidden />
						)}
						{isSubmitting ? "Sending resume" : "Submit resume"}
					</Button>
				</form>
			) : (
				<form className="candidate-passcode-form" onSubmit={redeem}>
					<div className="form-field">
						<Label htmlFor="application-passcode">
							Application passcode
						</Label>
						<Input
							autoComplete="one-time-code"
							id="application-passcode"
							maxLength={8}
							onChange={(event) => {
								setError(null);
								setPasscode(
									event.currentTarget.value
										.toUpperCase()
										.replace(/[^A-Z0-9]/g, "")
										.slice(0, 8),
								);
							}}
							pattern="[A-Z0-9]{8}"
							placeholder="AB12CD34"
							required
							value={passcode}
						/>
						<p className="form-hint">
							Passcodes work once and only while the job accepts
							submissions.
						</p>
					</div>
					<Button
						disabled={passcode.trim().length !== 8 || isRedeeming}
						type="submit"
					>
						{isRedeeming && (
							<ThinkingOrb
								aria-hidden
								size={20}
								state="solving"
							/>
						)}
						{isRedeeming ? "Checking passcode" : "Continue"}
					</Button>
				</form>
			)}

			{error && (
				<p className="form-error" role="alert">
					{error}
				</p>
			)}
		</section>
	);
};
