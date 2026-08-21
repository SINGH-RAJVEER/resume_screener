import { Button } from "@resume-screener/ui/components/button";
import {
	ArrowRight,
	BriefcaseBusiness,
	Check,
	FileSearch,
	Link2,
	UserRound,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Workspace } from "./features/workspace/Workspace";
import { authClient } from "./lib/auth-client";
import { CandidateHome } from "./pages/CandidateHome";

const App = () => {
	const { data: session, isPending } = authClient.useSession();

	if (isPending) {
		return (
			<main className="app-shell loading-page">
				<span className="status-dot" />
				Loading your workspace...
			</main>
		);
	}

	if (session?.user) {
		return session.user.accountType === "employer" ? (
			<Workspace />
		) : (
			<CandidateHome />
		);
	}

	return (
		<main className="public-page">
			<header className="public-header">
				<div className="brand-mark">
					<span>rs</span>
					<span className="brand-name">resume screener</span>
				</div>
				<nav>
					<a href="#how-it-works">How it works</a>
					<Link to="/sign-in">Sign in</Link>
					<Button asChild size="sm">
						<Link to="/sign-up?mode=candidate">Get started</Link>
					</Button>
				</nav>
			</header>

			<section className="public-hero">
				<div className="public-hero-copy">
					<p className="eyebrow">Evidence-backed resume evaluation</p>
					<h1>Understand the match. Verify the evidence.</h1>
					<p>
						Compare resumes with confirmed job requirements without
						reducing people to keyword counts or an unexplained
						score.
					</p>
					<div className="public-actions">
						<Button asChild size="lg">
							<Link to="/sign-up?mode=candidate">
								<UserRound />
								Check my resume
							</Link>
						</Button>
						<Button asChild size="lg" variant="outline">
							<Link to="/sign-up?mode=employer">
								<BriefcaseBusiness />
								I’m hiring
							</Link>
						</Button>
					</div>
					<ul className="trust-list">
						<li>
							<Check />
							Criterion-level reasoning
						</li>
						<li>
							<Check />
							Quoted source evidence
						</li>
						<li>
							<Check />
							Private by default
						</li>
					</ul>
				</div>

				<aside
					className="report-preview"
					aria-label="Example evaluation report"
				>
					<header>
						<span>Example evaluation</span>
						<strong>Private report</strong>
					</header>
					<div className="report-score">
						<span>Documented fit</span>
						<strong>
							84<small>/100</small>
						</strong>
						<p>92% evidence coverage</p>
					</div>
					<div className="report-criteria">
						<div>
							<span>React architecture</span>
							<b className="met">Met</b>
						</div>
						<div>
							<span>5+ years experience</span>
							<b className="partial">Partial</b>
						</div>
						<div>
							<span>System design</span>
							<b className="met">Met</b>
						</div>
					</div>
					<blockquote>
						“Owned the migration of a 40k-line frontend to a typed
						component system.”
					</blockquote>
				</aside>
			</section>

			<section className="workflow-section" id="how-it-works">
				<header>
					<p className="eyebrow">Choose your workflow</p>
					<h2>One product, two private workspaces.</h2>
				</header>
				<div className="workflow-grid">
					<article>
						<FileSearch />
						<span>For candidates</span>
						<h3>Check a resume or submit through an invitation.</h3>
						<p>
							Your independent reports remain private. Invited
							submissions share only the resume you choose with
							that employer.
						</p>
						<Link to="/sign-up?mode=candidate">
							Create candidate account <ArrowRight />
						</Link>
					</article>
					<article>
						<BriefcaseBusiness />
						<span>For employers</span>
						<h3>Confirm criteria before evaluating candidates.</h3>
						<p>
							Create jobs, review extracted requirements, upload
							resumes, and inspect the evidence behind each top
							match.
						</p>
						<Link to="/sign-up?mode=employer">
							Create employer account <ArrowRight />
						</Link>
					</article>
					<article>
						<Link2 />
						<span>Have an invitation?</span>
						<h3>Sign in, then paste or open your invitation.</h3>
						<p>
							Invitation links are single-use and job-scoped. They
							never expose the employer’s evaluation or hiring
							decision.
						</p>
						<Link to="/sign-in?mode=invited">
							Continue an invitation <ArrowRight />
						</Link>
					</article>
				</div>
			</section>
		</main>
	);
};

export default App;
