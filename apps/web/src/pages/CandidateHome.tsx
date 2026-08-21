import { Button } from "@resume-screener/ui/components/button";
import { authClient } from "../lib/auth-client";

export const CandidateHome = () => (
	<main className="app-shell">
		<section className="candidate-home">
			<p className="eyebrow">Candidate workspace</p>
			<h1>Your private resume evaluations will appear here.</h1>
			<p className="muted-copy">
				Independent evaluation and invitation submission flows are being
				added next.
			</p>
			<Button variant="outline" onClick={() => authClient.signOut()}>
				Sign out
			</Button>
		</section>
	</main>
);
