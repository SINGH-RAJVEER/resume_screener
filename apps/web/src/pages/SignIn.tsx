import { Button } from "@template/ui/components/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@template/ui/components/card";
import { Input } from "@template/ui/components/input";
import { Label } from "@template/ui/components/label";
import { type FormEvent, useState } from "react";
import { authClient } from "../lib/auth-client";

export const SignIn = () => {
    const [email, setEmail] = useState("");
    const [password, setPassword] = useState("");
    const [error, setError] = useState<string | null>(null);

    const handleSubmit = async (e: FormEvent<HTMLFormElement>) => {
        e.preventDefault();
        setError(null);

        const { error: authError } = await authClient.signIn.email({
            email,
            password,
            callbackURL: "/"
        });

        if (authError) setError(authError.message ?? "Sign in failed");
    };

    return (
        <main className="app-shell auth-page">
            <Card className="auth-card">
                <form onSubmit={handleSubmit}>
                    <CardHeader>
                        <CardTitle className="auth-title">Sign In</CardTitle>
                    </CardHeader>
                    <CardContent className="auth-fields">
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
                                autoComplete="current-password"
                                value={password}
                                onChange={(event) => setPassword(event.currentTarget.value)}
                                required
                            />
                        </div>
                        {error && <p className="form-error">{error}</p>}
                    </CardContent>
                    <CardFooter className="auth-footer">
                        <Button type="submit" className="auth-submit">
                            Sign In
                        </Button>
                        <p className="auth-switch">
                            <a className="auth-link" href="/sign-up">
                                Sign Up
                            </a>
                        </p>
                    </CardFooter>
                </form>
            </Card>
        </main>
    );
};
