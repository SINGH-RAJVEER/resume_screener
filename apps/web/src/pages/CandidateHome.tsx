import { Button } from "@resume-screener/ui/components/button";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import {
	ArrowRight,
	CheckCircle2,
	FileSearch,
	Link2,
	UploadCloud,
} from "lucide-react";
import { type FormEvent, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { candidateClient } from "../features/candidate/client";
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

	const redeem = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		const token = tokenFromValue(invitationValue);
		if (!token) return;
		setError(null);
		setIsWorking(true);
		try {
			const result = await candidateClient.redeemInvitation(token);
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
										Invitation link or token
									</Label>
									<Input
										id="invitation"
										onChange={(event) =>
											setInvitationValue(
												event.currentTarget.value,
											)
										}
										placeholder="Paste the invitation you received"
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

					<section className="candidate-action candidate-action-muted">
						<div className="candidate-action-heading">
							<FileSearch />
							<div>
								<h2>Private resume check</h2>
								<p>
									Compare your resume with a job description.
								</p>
							</div>
						</div>
						<p>
							This workflow is not available in the current build.
							Your invitation submission above is fully supported.
						</p>
						<Button disabled variant="outline">
							Coming next
						</Button>
					</section>
				</div>
			</section>
		</main>
	);
};
