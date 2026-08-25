import { ThinkingOrb } from "thinking-orbs";
import { Workspace } from "./features/workspace/Workspace";
import { authClient } from "./lib/auth-client";
import { CandidateHome } from "./pages/CandidateHome";
import { Landing } from "./pages/Landing";

const App = () => {
	const { data: session, isPending } = authClient.useSession();

	if (isPending) {
		return (
			<main className="app-shell loading-page" role="status">
				<ThinkingOrb aria-hidden size={64} state="solving" />
				<p>Loading...</p>
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

	return <Landing />;
};

export default App;
