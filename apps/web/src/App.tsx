import { Button } from "@resume-screener/ui/components/button";
import {
	Card,
	CardContent,
	CardFooter,
} from "@resume-screener/ui/components/card";
import { Link } from "react-router-dom";
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

	return (
		<main className="app-shell">
			<Card className="home-card">
				<CardContent>
					{session?.user ? (
						<div className="session-panel">
							<p className="muted-copy">Signed in as</p>
							<p className="session-name">{session.user.name}</p>
							<p className="muted-copy">{session.user.email}</p>
						</div>
					) : (
						<p className="muted-copy home-prompt">
							Create an account or sign in.
						</p>
					)}
				</CardContent>
				<CardFooter className="home-actions">
					{session?.user ? (
						<Button
							type="button"
							variant="outline"
							onClick={() => authClient.signOut()}
						>
							Sign out
						</Button>
					) : (
						<>
							<Button asChild>
								<Link to="/sign-up">Create account</Link>
							</Button>
							<Button asChild variant="outline">
								<Link to="/sign-in">Sign in</Link>
							</Button>
						</>
					)}
				</CardFooter>
			</Card>
		</main>
	);
};

export default App;
