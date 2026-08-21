import { Button } from "@resume-screener/ui/components/button";
import { Link } from "react-router-dom";
import { Workspace } from "./features/workspace/Workspace";
import { authClient } from "./lib/auth-client";
import { CandidateHome } from "./pages/CandidateHome";

const App = () => {
	const { data: session, isPending } = authClient.useSession();

	if (isPending) return <main className="app-shell">Loading...</main>;
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
				<strong>resume screener</strong>
				<nav>
					<Link to="/sign-in">Sign in</Link>
					<Button asChild size="sm">
						<Link to="/sign-up?mode=candidate">Create account</Link>
					</Button>
				</nav>
			</header>
			<section className="public-hero">
				<h1>Resume evaluation with evidence.</h1>
				<p>Choose a workspace.</p>
				<div className="public-actions">
					<Button asChild>
						<Link to="/sign-up?mode=candidate">Candidate</Link>
					</Button>
					<Button asChild variant="outline">
						<Link to="/sign-up?mode=employer">Employer</Link>
					</Button>
				</div>
			</section>
		</main>
	);
};

export default App;
