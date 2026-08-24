import { Button } from "@skillsignal/ui/components/button";
import { ClipboardCheck, FileSearch } from "lucide-react";
import { useState } from "react";
import { CandidateSubmissionWorkspace } from "../features/candidate/CandidateSubmissionWorkspace";
import { PrivateEvaluationWorkspace } from "../features/candidate/PrivateEvaluationWorkspace";
import { authClient } from "../lib/auth-client";

type CandidateTask = "private-check" | "job-submission";

export const CandidateHome = () => {
	const { data: session } = authClient.useSession();
	const [task, setTask] = useState<CandidateTask>("private-check");

	return (
		<main className="candidate-page">
			<header className="candidate-header">
				<div className="brand-mark">
					<img src="/icon.webp" alt="SkillSignal" />
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
					<h1>Your resume stays yours.</h1>
					<p>
						Check it privately, or send one document to an employer
						who gave you an application passcode.
					</p>
				</header>

				<nav
					aria-label="Candidate tasks"
					className="candidate-task-nav"
				>
					<Button
						aria-pressed={task === "private-check"}
						onClick={() => setTask("private-check")}
						variant="ghost"
					>
						<FileSearch />
						Private resume check
					</Button>
					<Button
						aria-pressed={task === "job-submission"}
						onClick={() => setTask("job-submission")}
						variant="ghost"
					>
						<ClipboardCheck />
						Employer submission
					</Button>
				</nav>

				{task === "private-check" ? (
					<PrivateEvaluationWorkspace />
				) : (
					<CandidateSubmissionWorkspace />
				)}
			</section>
		</main>
	);
};
