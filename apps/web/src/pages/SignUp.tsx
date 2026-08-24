import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { ArrowLeft, BriefcaseBusiness, UserRound } from "lucide-react";
import { type FormEvent, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authClient } from "../lib/auth-client";

type AccountType = "candidate" | "employer";

export const SignUp = () => {
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
	const [name, setName] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [isSubmitting, setIsSubmitting] = useState(false);
	const [error, setError] = useState<string | null>(null);

	const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		setError(null);
		setIsSubmitting(true);

		const result = await (accountType === "employer"
			? authClient.signUp.employer
			: authClient.signUp.email)({ name, email, password });

		setIsSubmitting(false);
		if (result.error) {
			setError(result.error.message ?? "Account creation failed");
			return;
		}
		navigate(destination);
	};

	const signInPath =
		accountType === "employer"
			? "/sign-in?mode=employer"
			: isInvited
				? `/sign-in?mode=invited${invitation ? `&invitation=${invitation}` : ""}${returnTo ? `&returnTo=${encodeURIComponent(returnTo)}` : ""}`
				: "/sign-in?mode=candidate";

	return (
		<main className="auth-page">
			<Link className="auth-back" to="/">
				<ArrowLeft /> Back to home
			</Link>
			<section className="auth-panel" aria-labelledby="sign-up-title">
				<div className="brand-mark auth-brand">
					<img src="/icon.webp" alt="SkillSignal" />
				</div>
				<header className="auth-heading">
					<h1 id="sign-up-title">Create your account</h1>
					<p>
						Account types are separate so candidate data and
						employer data stay isolated.
					</p>
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
							<small>Evaluate or submit a resume</small>
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
								<small>Create jobs and review evidence</small>
							</span>
						</button>
					)}
				</fieldset>

				{isInvited && accountType === "candidate" && (
					<p className="auth-context">
						Create a candidate account to continue your invited
						submission.
					</p>
				)}

				<form className="auth-form" onSubmit={handleSubmit}>
					<div className="form-field">
						<Label htmlFor="name">Full name</Label>
						<Input
							autoComplete="name"
							id="name"
							onChange={(event) =>
								setName(event.currentTarget.value)
							}
							required
							value={name}
						/>
					</div>
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
							autoComplete="new-password"
							id="password"
							maxLength={72}
							minLength={8}
							onChange={(event) =>
								setPassword(event.currentTarget.value)
							}
							required
							type="password"
							value={password}
						/>
						<p className="form-hint">Use at least 8 characters.</p>
					</div>
					{error && (
						<p className="form-error" role="alert">
							{error}
						</p>
					)}
					<Button disabled={isSubmitting} size="lg" type="submit">
						{isSubmitting
							? "Creating account..."
							: `Create ${accountType} account`}
					</Button>
				</form>

				<p className="auth-switch">
					Already registered? <Link to={signInPath}>Sign in</Link>
				</p>
			</section>
		</main>
	);
};
