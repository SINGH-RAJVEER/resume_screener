import { Button } from "@template/ui/components/button";
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from "@template/ui/components/card";
import { Input } from "@template/ui/components/input";
import { Label } from "@template/ui/components/label";
import { type FormEvent, useState } from "react";
import { authClient } from "../lib/auth-client";

export const SignUp = () => {
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
            callbackURL: "/"
        });

        if (authError) {
            setError(authError.message ?? "Sign up failed");
        }
    };

    return (
        <main className="app-shell auth-page">
            <Card className="auth-card">
                <form onSubmit={handleSubmit}>
                    <CardHeader>
                        <CardTitle className="auth-title">Sign Up</CardTitle>
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
                        <Button type="submit" className="auth-submit">
                            Sign Up
                        </Button>
                        <p className="auth-switch">
                            <a className="auth-link" href="/sign-in">
                                Sign in
                            </a>
                        </p>
                    </CardFooter>
                </form>
            </Card>
        </main>
    );
};
