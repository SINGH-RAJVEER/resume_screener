import { Button } from "@template/ui/components/button";
import { Card, CardContent, CardFooter } from "@template/ui/components/card";
import { authClient } from "./lib/auth-client";

const App = () => {
    const { data: session } = authClient.useSession();

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
                        <p className="muted-copy home-prompt">Create an account or sign in.</p>
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
                                <a href="/sign-up">Create account</a>
                            </Button>
                            <Button asChild variant="outline">
                                <a href="/sign-in">Sign in</a>
                            </Button>
                        </>
                    )}
                </CardFooter>
            </Card>
        </main>
    );
};

export default App;
