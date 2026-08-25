import { Button } from "@skillsignal/ui/components/button";
import { useState } from "react";
import { Link } from "react-router-dom";
import type { TourAct } from "../features/tour/types";
import { authClient } from "../lib/auth-client";

const DEMO_ACT_KEY = "skillsignal-demo-act";
const DEMO_INDEX_KEY = "skillsignal-demo-index";
const DEMO_USER_KEY = "skillsignal-demo-user";

const AUDIENCES = [
	{
		name: "Candidate",
		headline: "Evaluate your own resume.",
		copy: "Run independent evaluations against any job description and get an evidence-backed report that stays private to you.",
		cta: "Create a candidate account",
		to: "/sign-up?mode=candidate",
	},
	{
		name: "Employer organization",
		headline: "Screen submissions against confirmed requirements.",
		copy: "Own jobs and requirements in one place, invite candidates with links, and run batch evaluations across every submission.",
		cta: "Create an employer account",
		to: "/sign-up?mode=employer",
	},
];

export const Landing = () => {
	const [startingDemo, setStartingDemo] = useState<TourAct | null>(null);
	const [demoError, setDemoError] = useState<string | null>(null);

	const startDemo = async (act: TourAct) => {
		setStartingDemo(act);
		setDemoError(null);
		sessionStorage.removeItem(DEMO_ACT_KEY);
		sessionStorage.removeItem(DEMO_INDEX_KEY);
		sessionStorage.removeItem(DEMO_USER_KEY);
		const result = await authClient.demo(act);
		if (result.data) {
			sessionStorage.setItem(DEMO_ACT_KEY, act);
			sessionStorage.setItem(DEMO_INDEX_KEY, "0");
			sessionStorage.setItem(DEMO_USER_KEY, result.data.user.id);
		} else {
			setDemoError(
				result.error.message === "Unable to reach the API"
					? "The guided demo needs the API to be running."
					: "The guided demo could not start. Try again.",
			);
		}
		setStartingDemo(null);
	};

	return (
		<main className="public-page">
			<header className="public-header">
				<div className="brand-mark">
					<img src="/icon.webp" alt="SkillSignal" />
				</div>
				<nav>
					<Link to="/sign-in">Sign in</Link>
					<Button asChild size="sm">
						<Link to="/sign-up?mode=candidate">Sign up</Link>
					</Button>
				</nav>
			</header>

			<section className="public-hero">
				<h1>Resume evaluation with evidence.</h1>
				<p className="hero-copy">
					Scores are only as good as their proof. Every evaluation
					quotes the lines of the resume that earned it, against
					requirements you confirmed.
				</p>
				<div className="public-actions">
					<Button
						disabled={startingDemo !== null}
						onClick={() => void startDemo("employer")}
					>
						{startingDemo === "employer"
							? "Starting the demo..."
							: "See how it works"}
					</Button>
				</div>
				{demoError && (
					<p className="form-error" role="alert">
						{demoError}
					</p>
				)}
			</section>

			<section className="landing-audiences">
				{AUDIENCES.map((audience) => (
					<article key={audience.name} className="landing-audience">
						<p className="eyebrow">{audience.name}</p>
						<h2>{audience.headline}</h2>
						<p>{audience.copy}</p>
						<Button asChild variant="outline" size="sm">
							<Link to={audience.to}>{audience.cta}</Link>
						</Button>
					</article>
				))}
			</section>

			<footer className="public-footer">
				<span>
					Evaluations compare one resume submission with one confirmed
					job version.
				</span>
			</footer>
		</main>
	);
};
