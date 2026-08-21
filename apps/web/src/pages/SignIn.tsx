import { Button } from "@resume-screener/ui/components/button";
import {
	Card,
	CardContent,
	CardFooter,
	CardHeader,
	CardTitle,
} from "@resume-screener/ui/components/card";
import { Input } from "@resume-screener/ui/components/input";
import { Label } from "@resume-screener/ui/components/label";
import { type FormEvent, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { authClient } from "../lib/auth-client";

export const SignIn = () => {
	const navigate = useNavigate();
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string | null>(null);

	const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
		e.preventDefault();
		setError(null);

		const { error: authError } = await authClient.signIn.email({
			email,
			password,
		});

		if (authError) {
			setError(authError.message ?? "Sign in failed");
			return;
		}
		navigate("/");
	};

	return (
		<main className="auth-shell">
			<section className="auth-aside">
				<div className="brand-mark">
					<span>rs</span>
					<span className="brand-name">resume screener</span>
				</div>
				<div>
					<p className="eyebrow">A better signal</p>
					<h1>Return to the evidence.</h1>
					<p>
						Keep your private evaluations, job criteria, and
						documented matches in one quiet workspace.
					</p>
				</div>
				<div className="auth-aside-footer">
					<span className="status-dot" /> Your reports stay private to
					you.
				</div>
			</section>
			<section className="auth-form-area">
				<Card className="auth-card">
					<form onSubmit={handleSubmit}>
						<CardHeader>
							<CardTitle asChild className="auth-title">
								<h1>Sign In</h1>
							</CardTitle>
						</CardHeader>
						<CardContent className="auth-fields">
							<div className="form-field">
								<Label htmlFor="email">Email</Label>
								<Input
									id="email"
									type="email"
									autoComplete="email"
									value={email}
									onChange={(event) =>
										setEmail(event.currentTarget.value)
									}
									required
								/>
							</div>
							<div className="form-field">
								<Label htmlFor="password">Password</Label>
								<Input
									id="password"
									type="password"
									autoComplete="current-password"
									value={password}
									onChange={(event) =>
										setPassword(event.currentTarget.value)
									}
									required
								/>
							</div>
							{error && <p className="form-error">{error}</p>}
						</CardContent>
						<CardFooter className="auth-footer">
							<Button type="submit" className="w-full">
								Sign In
							</Button>
							<p className="auth-switch">
								<Link className="auth-link" to="/sign-up">
									Sign Up
								</Link>
							</p>
						</CardFooter>
					</form>
				</Card>
			</section>
		</main>
	);
};
