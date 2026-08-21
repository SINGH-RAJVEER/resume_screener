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
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { authClient } from "../lib/auth-client";

export const SignUp = () => {
	const navigate = useNavigate();
	const [searchParams] = useSearchParams();
	const mode = searchParams.get("mode");
	const modeLabel =
		mode === "employer"
			? "an organization workspace"
			: "your private evaluation";
	const [name, setName] = useState("");
	const [email, setEmail] = useState("");
	const [password, setPassword] = useState("");
	const [error, setError] = useState<string | null>(null);

	const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
		e.preventDefault();
		setError(null);

		const { error: authError } = await authClient.signUp.email({
			name,
			email,
			password,
		});

		if (authError) {
			setError(authError.message ?? "Sign up failed");
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
					<p className="eyebrow">Start with clarity</p>
					<h1>Make your next application legible.</h1>
					<p>
						Compare your resume with a real job description and
						understand the evidence behind every result.
					</p>
				</div>
				<div className="auth-aside-footer">
					<span className="status-dot" /> One free independent
					evaluation every week.
				</div>
			</section>
			<section className="auth-form-area">
				<Card className="auth-card">
					<form onSubmit={handleSubmit}>
						<CardHeader>
							<CardTitle asChild className="auth-title">
								<h1>Create {modeLabel}</h1>
							</CardTitle>
						</CardHeader>
						<CardContent className="auth-fields">
							<div className="form-field">
								<Label htmlFor="name">Name</Label>
								<Input
									id="name"
									type="text"
									autoComplete="name"
									value={name}
									onChange={(event) =>
										setName(event.currentTarget.value)
									}
									required
								/>
							</div>
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
									minLength={8}
									maxLength={72}
									autoComplete="new-password"
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
								Sign Up
							</Button>
							<p className="auth-switch">
								<Link className="auth-link" to="/sign-in">
									Sign in
								</Link>
							</p>
						</CardFooter>
					</form>
				</Card>
			</section>
		</main>
	);
};
