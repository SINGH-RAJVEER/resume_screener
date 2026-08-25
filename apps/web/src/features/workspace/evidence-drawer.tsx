import { X } from "lucide-react";
import type { Evaluation } from "./client";
import { eligibilityChipClass, outcomeChipClass } from "./shared";

export const EvidenceDrawer = ({
	evaluation,
	onClose,
}: {
	evaluation: Evaluation;
	onClose: () => void;
}) => (
	<div className="drawer-panel">
		<header className="drawer-head">
			<div>
				<p className="eyebrow">Evidence inspection</p>
				<h2 id="evidence-title">
					{evaluation.candidateName ?? "Candidate"}
				</h2>
				<div className="drawer-stats">
					<span className="score-cell">
						{evaluation.score ?? "—"}
						<span className="score-denominator">/100</span>
					</span>
					<span
						className={eligibilityChipClass(evaluation.eligibility)}
					>
						{evaluation.eligibility.replace(/_/g, " ")}
					</span>
					{evaluation.candidateEmail && (
						<span className="muted-copy">
							{evaluation.candidateEmail}
						</span>
					)}
					{evaluation.candidateLocation && (
						<span className="muted-copy">
							{evaluation.candidateLocation}
						</span>
					)}
				</div>
			</div>
			<button
				aria-label="Close evidence inspection"
				className="icon-button"
				onClick={onClose}
				type="button"
			>
				<X />
			</button>
		</header>

		{(evaluation.qualityWarnings?.length ?? 0) > 0 && (
			<section className="drawer-quality" aria-labelledby="quality-title">
				<h3 id="quality-title">Data quality</h3>
				<ul>
					{evaluation.qualityWarnings?.map((warning) => (
						<li key={warning}>{warning}</li>
					))}
				</ul>
				{evaluation.extractionMetadata?.pageCount !== undefined && (
					<p>
						{evaluation.extractionMetadata?.pageCount} page
						{evaluation.extractionMetadata?.pageCount === 1
							? ""
							: "s"}
						, {evaluation.extractionMetadata?.blockCount ?? 0}{" "}
						evidence blocks
					</p>
				)}
			</section>
		)}

		{(evaluation.hardGates?.length ?? 0) > 0 && (
			<section className="drawer-quality" aria-labelledby="gates-title">
				<h3 id="gates-title">Hard gates</h3>
				<ul>
					{evaluation.hardGates?.map((gate) => (
						<li key={gate.requirement}>
							{gate.requirement} —{" "}
							{gate.outcome.replace(/_/g, " ")}
						</li>
					))}
				</ul>
			</section>
		)}

		{(evaluation.assessments ?? []).length === 0 ? (
			<p className="muted-copy">
				Evaluations appear here once processing completes.
			</p>
		) : (
			evaluation.assessments.map((assessment) => (
				<div className="assessment-card" key={assessment.requirement}>
					<div className="assessment-top">
						<p>{assessment.requirement}</p>
						<span className={outcomeChipClass(assessment.outcome)}>
							{assessment.outcome.replace(/_/g, " ")}
						</span>
					</div>
					{(assessment.kind === "hard_gate" ||
						assessment.contribution != null) && (
						<p className="assessment-weight">
							{assessment.kind === "hard_gate"
								? "Hard gate, excluded from the score"
								: `Weight ${assessment.weight ?? 1} · ${
										assessment.contribution
									}% of the score`}
						</p>
					)}
					<p className="assessment-reasoning">
						{assessment.reasoning}
					</p>
					{assessment.evidence.length > 0 && (
						<div className="assessment-evidence">
							{assessment.evidence.map((item) => (
								<blockquote
									className="evidence-quote"
									key={`${item.blockId}-${item.quote}`}
								>
									“{item.quote}”
									<cite>Source block: {item.blockId}</cite>
								</blockquote>
							))}
						</div>
					)}
					{assessment.semanticEvidence?.matches?.length ? (
						<div className="assessment-evidence">
							<p className="eyebrow">Related passages</p>
							{assessment.semanticEvidence.matches.map(
								(match) => (
									<blockquote
										className="evidence-quote"
										key={`semantic-${match.blockId}`}
									>
										{match.text || match.blockId}
										<cite>
											Similarity{" "}
											{Math.round(match.similarity * 100)}
											%
										</cite>
									</blockquote>
								),
							)}
						</div>
					) : null}
				</div>
			))
		)}
	</div>
);
