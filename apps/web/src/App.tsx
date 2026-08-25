import { ThinkingOrb } from "thinking-orbs";
import { TOUR_STEPS } from "./features/tour/steps";
import { TourProvider } from "./features/tour/TourProvider";
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
		return (
			<TourProvider
				sessionAccountType={session.user.accountType}
				sessionUserId={session.user.id}
				steps={TOUR_STEPS}
			>
				{session.user.accountType === "employer" ? (
					<Workspace />
				) : (
					<CandidateHome />
				)}
			</TourProvider>
		);
	}

	return <Landing />;
};

export default App;
