import { Button } from "@skillsignal/ui/components/button";
import { Link } from "react-router-dom";

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

export const Landing = () => (
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
				Scores are only as good as their proof. Every evaluation quotes the lines of the resume that earned it, against requirements you confirmed.
			</p>
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
				Evaluations compare one resume submission with one confirmed job version.
			</span>
			<Link to="/sign-in">Sign in</Link>
		</footer>
	</main>
);
