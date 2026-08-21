import { Link } from "react-router-dom";
import { Workspace } from "./features/workspace/Workspace";
import { authClient } from "./lib/auth-client";

const App = () => {
	const { data: session, isPending } = authClient.useSession();

	if (isPending) {
		return (
			<main className="app-shell">
				<p className="muted-copy">Checking your session...</p>
			</main>
		);
	}

	if (session?.user) return <Workspace />;
	return (
		<main className="landing-shell">
			<section className="landing-copy">
				<div className="brand-mark">
					<span>rs</span>
					<span className="brand-name">resume screener</span>
				</div>
				<p className="eyebrow">Evidence before instinct</p>
				<h1>See the signal in every resume.</h1>
				<p className="landing-lede">
					A calmer way to compare documented experience with the
					requirements that actually matter.
				</p>
				<section className="landing-paths" aria-labelledby="path-label">
					<p className="path-label" id="path-label">
						What brings you here?
					</p>
					<Link
						className="landing-path"
						to="/sign-up?mode=independent"
					>
						<span>
							<b>01</b>
							<strong>Check my resume</strong>
							<small>
								Compare your experience with a job description.
							</small>
						</span>
						<i aria-hidden="true">↗</i>
					</Link>
					<Link className="landing-path" to="/sign-up?mode=employer">
						<span>
							<b>02</b>
							<strong>Screen for an organization</strong>
							<small>
								Create jobs and review candidate submissions.
							</small>
						</span>
						<i aria-hidden="true">↗</i>
					</Link>
					<div className="landing-path landing-path-note">
						<span>
							<b>03</b>
							<strong>Submit through an invitation</strong>
							<small>
								Open the job-scoped link you received to upload.
							</small>
						</span>
					</div>
					<Link className="button button-quiet" to="/sign-in">
						Already have an account? Sign in{" "}
						<span aria-hidden="true">→</span>
					</Link>
				</section>
				<div className="landing-note">
					<span className="status-dot" /> One free independent
					evaluation every week
				</div>
			</section>
			<aside className="landing-preview" aria-label="Product preview">
				<div className="preview-topline">
					<span>evaluation / 024</span>
					<span>private report</span>
				</div>
				<div className="preview-score">
					<strong>84</strong>
					<span>
						/ 100
						<br />
						<small>documented fit</small>
					</span>
				</div>
				<div className="preview-rule" />
				<div className="preview-row">
					<span>React architecture</span>
					<b className="outcome-met">Met</b>
				</div>
				<div className="preview-row">
					<span>5+ years experience</span>
					<b className="outcome-partial">Partial</b>
				</div>
				<div className="preview-row">
					<span>Evidence coverage</span>
					<b>92%</b>
				</div>
				<blockquote>
					“Owned the migration of a 40k-line frontend to a typed
					component system.”
				</blockquote>
			</aside>
		</main>
	);
};

export default App;
