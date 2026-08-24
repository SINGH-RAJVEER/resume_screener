import { Button } from "@resume-screener/ui/components/button";
import { Link } from "react-router-dom";

const FLOW_STEPS = [
	{
		step: "01",
		title: "Confirm requirements",
		copy: "Recruiters confirm each job requirement as required, preferred, ignored, or a hard gate before any resume is read.",
	},
	{
		step: "02",
		title: "Collect submissions",
		copy: "Resumes arrive as versioned documents, uploaded by the employer or through a job-scoped invitation link.",
	},
	{
		step: "03",
		title: "Read the evaluation",
		copy: "Every score cites evidence quoted from the resume. Failed hard gates mark an evaluation not eligible.",
	},
];

const AUDIENCES = [
	{
		name: "Candidate",
		headline: "Evaluate your own resume first.",
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
			<strong>resume screener</strong>
			<nav>
				<Link to="/sign-in">Sign in</Link>
				<Button asChild size="sm">
					<Link to="/sign-up?mode=candidate">Create account</Link>
				</Button>
			</nav>
		</header>

		<section className="public-hero">
			<p className="eyebrow">Evidence-backed screening</p>
			<h1>Resume evaluation with evidence.</h1>
			<p>
				Scores are only as good as their proof. Every evaluation quotes
				the lines of the resume that earned it, against requirements you
				confirmed.
			</p>
			<div className="public-actions">
				<Button asChild>
					<Link to="/sign-up?mode=candidate">Start as candidate</Link>
				</Button>
				<Button asChild variant="outline">
					<Link to="/sign-up?mode=employer">Start as employer</Link>
				</Button>
			</div>
		</section>

		<section className="landing-flow">
			<h2 className="section-kicker">How an evaluation runs</h2>
			<ol className="landing-steps">
				{FLOW_STEPS.map((item) => (
					<li key={item.step} className="landing-step">
						<span className="landing-step-index">{item.step}</span>
						<strong>{item.title}</strong>
						<p>{item.copy}</p>
					</li>
				))}
			</ol>
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
				Evaluations compare one resume submission with one confirmed job
				version.
			</span>
			<Link to="/sign-in">Sign in</Link>
		</footer>
	</main>
);
