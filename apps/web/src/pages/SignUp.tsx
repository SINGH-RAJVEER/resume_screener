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

export const SignUp = () => {
	const navigate = useNavigate();
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
		<main className="app-shell">
			<Card className="auth-card">
				<form onSubmit={handleSubmit}>
					<CardHeader>
						<CardTitle asChild className="auth-title">
							<h1>Sign Up</h1>
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
								onChange={(event) => setName(event.currentTarget.value)}
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
								onChange={(event) => setEmail(event.currentTarget.value)}
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
								onChange={(event) => setPassword(event.currentTarget.value)}
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
		</main>
	);
};
