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
		<main className="app-shell">
			<p className="muted-copy">
				Create an account or{" "}
				<Link className="auth-link" to="/sign-in">
					sign in
				</Link>{" "}
				to create jobs and queue resume submissions.
			</p>
		</main>
	);
};

export default App;
