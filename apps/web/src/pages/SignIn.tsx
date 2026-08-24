import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { ArrowLeft, BriefcaseBusiness, UserRound } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authClient } from "../lib/auth-client";

type AccountType = "candidate" | "employer";

export const SignIn = () => {
	const navigate = useNavigate();
	const [searchParams] = useSearchParams();
	const invitation = searchParams.get("invitation");
	const returnTo = searchParams.get("returnTo");
	const isInvited =
		searchParams.get("mode") === "invited" || invitation !== null;
	const destination =
		returnTo?.startsWith("/") && !returnTo.startsWith("//")
			? returnTo
			: invitation
				? `/?invitation=${invitation}`
				: "/";
	const [accountType, setAccountType] = useState<AccountType>(
		searchParams.get("mode") === "employer" ? "employer" : "candidate",
	);
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setError(null);
		setIsSubmitting(true);

		const result = await (accountType === "employer"
			? authClient.signIn.employer
			: authClient.signIn.email)({ email, password });

		setIsSubmitting(false);
		if (result.error) {
			setError(result.error.message ?? "Sign in failed");
			return;
		}
		navigate(destination);
	};

	const signUpPath =
		accountType === "employer"
			? "/sign-up?mode=employer"
			: isInvited
				? `/sign-up?mode=invited${invitation ? `&invitation=${invitation}` : ""}${returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : ""}`
				: "/sign-up?mode=candidate";

	return (
		<main className="auth-page">
			<Link className="auth-back" to="/">
				<ArrowLeft /> Back to home
			</Link>
			<section className="auth-panel" aria-labelledby="sign-in-title">
				<div className="brand-mark auth-brand">
					<span>rs</span>
					<span className="brand-name">SkillSignal</span>
				</div>
				<header className="auth-heading">
					<h1 id="sign-in-title">Welcome back</h1>
					<p>Choose the workspace attached to your account.</p>
				</header>

				<fieldset className="account-type-control">
					<legend>Account type</legend>
					<button
						className={accountType === "candidate" ? "active" : ""}
						onClick={() => setAccountType("candidate")}
						type="button"
					>
						<UserRound />
						<span>
							<strong>Candidate</strong>
							<small>My resume and invitations</small>
						</span>
					</button>
					{!isInvited && (
						<button
							className={
								accountType === "employer" ? "active" : ""
							}
							onClick={() => setAccountType("employer")}
							type="button"
						>
							<BriefcaseBusiness />
							<span>
								<strong>Employer</strong>
								<small>Jobs and candidate review</small>
							</span>
						</button>
					)}
				</fieldset>

				{isInvited && accountType === "candidate" && (
					<p className="auth-context">
						Sign in to continue your invited resume submission.
					</p>
				)}

				<form className="auth-form" onSubmit={handleSubmit}>
					<div className="form-field">
						<Label htmlFor="email">Email address</Label>
						<Input
							autoComplete="email"
							id="email"
							onChange={(event) =>
								setEmail(event.currentTarget.value)
							}
							required
							type="email"
							value={email}
						/>
					</div>
					<div className="form-field">
						<Label htmlFor="password">Password</Label>
						<Input
							autoComplete="current-password"
							id="password"
							onChange={(event) =>
								setPassword(event.currentTarget.value)
							}
							required
							type="password"
							value={password}
						/>
					</div>
					{error && (
						<p className="form-error" role="alert">
							{error}
						</p>
					)}
					<Button disabled={isSubmitting} size="lg" type="submit">
						{isSubmitting
							? "Signing in..."
							: `Sign in as ${accountType}`}
					</Button>
				</form>

				<p className="auth-switch">
					New here? <Link to={signUpPath}>Create an account</Link>
				</p>
			</section>
		</main>
	);
};
