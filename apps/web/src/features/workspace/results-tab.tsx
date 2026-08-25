import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Download, FileText, UploadCloud } from "lucide-react";
import { ThinkingOrb } from "thinking-orbs";
import type { Evaluation } from "./client";
import {
	type EligibilityFilter,
	eligibilityChipClass,
	type OutcomeFilter,
	type StatusFilter,
} from "./shared";

type ResultsTabProps = {
	evaluations: Evaluation[];
	visibleEvaluations: Evaluation[];
	evaluationQuery: string;
	eligibilityFilter: EligibilityFilter;
	outcomeFilter: OutcomeFilter;
	statusFilter: StatusFilter;
	skillFilter: string;
	minimumScoreText: string;
	setEvaluationQuery: (value: string) => void;
	setEligibilityFilter: (value: EligibilityFilter) => void;
	setOutcomeFilter: (value: OutcomeFilter) => void;
	setStatusFilter: (value: StatusFilter) => void;
	setSkillFilter: (value: string) => void;
	setMinimumScoreText: (value: string) => void;
	exportCsv: () => void;
	onQueue: () => void;
	onInspect: (evaluation: Evaluation) => void;
};

export const ResultsTab = ({
	evaluations,
	visibleEvaluations,
	evaluationQuery,
	eligibilityFilter,
	outcomeFilter,
	statusFilter,
	skillFilter,
	minimumScoreText,
	setEvaluationQuery,
	setEligibilityFilter,
	setOutcomeFilter,
	setStatusFilter,
	setSkillFilter,
	setMinimumScoreText,
	exportCsv,
	onQueue,
	onInspect,
}: ResultsTabProps) => {
	const eligibleCount = evaluations.filter(
		(evaluation) => evaluation.eligibility === "eligible",
	).length;
	const reviewCount = evaluations.filter(
		(evaluation) => evaluation.eligibility === "needs_review",
	).length;
	const topScore = evaluations.find(
		(evaluation) => evaluation.score !== null,
	)?.score;

	return (
		<div className="workspace-stage-gap" data-tour="tab-results">
			<div className="stat-strip">
				<div className="stat">
					<span>Evaluated</span>
					<p>{evaluations.length}</p>
				</div>
				<div className="stat">
					<span>Top score</span>
					<p>{topScore ?? "—"}</p>
				</div>
				<div className="stat">
					<span>Eligible</span>
					<p>{eligibleCount}</p>
				</div>
				<div className="stat">
					<span>Needs review</span>
					<p>{reviewCount}</p>
				</div>
			</div>

			<div className="filter-bar">
				<div className="filter-group">
					<Input
						aria-label="Search candidates"
						onChange={(event) =>
							setEvaluationQuery(event.target.value)
						}
						placeholder="Search name or email..."
						value={evaluationQuery}
					/>
					<select
						aria-label="Filter by eligibility"
						className="workspace-filter-select"
						data-tour="eligibility-filter"
						onChange={(event) =>
							setEligibilityFilter(
								event.target.value as EligibilityFilter,
							)
						}
						value={eligibilityFilter}
					>
						<option value="top">Top matches</option>
						<option value="all">All outcomes</option>
						<option value="eligible">Eligible</option>
						<option value="needs_review">Needs review</option>
						<option value="not_eligible">Not eligible</option>
					</select>
					<select
						aria-label="Filter by requirement outcome"
						className="workspace-filter-select"
						onChange={(event) =>
							setOutcomeFilter(
								event.target.value as OutcomeFilter,
							)
						}
						value={outcomeFilter}
					>
						<option value="all">Any requirement outcome</option>
						<option value="met">Has met requirement</option>
						<option value="partial">Has partial requirement</option>
						<option value="not_met">Has unmet requirement</option>
						<option value="unknown">Has unknown requirement</option>
					</select>
					<select
						aria-label="Filter by processing state"
						className="workspace-filter-select"
						onChange={(event) =>
							setStatusFilter(event.target.value as StatusFilter)
						}
						value={statusFilter}
					>
						<option value="all">Any processing state</option>
						<option value="pending">Pending</option>
						<option value="processing">Processing</option>
						<option value="complete">Complete</option>
						<option value="failed">Failed</option>
					</select>
					<Input
						aria-label="Filter by skill"
						onChange={(event) => setSkillFilter(event.target.value)}
						placeholder="Skill..."
						value={skillFilter}
					/>
					<label className="filter-minimum">
						Min score
						<input
							aria-label="Minimum score"
							max={100}
							min={0}
							onChange={(event) =>
								setMinimumScoreText(event.target.value)
							}
							placeholder="0"
							type="number"
							value={minimumScoreText}
						/>
					</label>
				</div>
				<Button onClick={exportCsv} size="sm" variant="outline">
					<Download />
					Export CSV
				</Button>
			</div>

			<div className="results-table">
				<table>
					<thead>
						<tr>
							<th scope="col">Candidate</th>
							<th scope="col">Score</th>
							<th scope="col">Eligibility</th>
							<th scope="col">Hard gates</th>
							<th scope="col">Evidence coverage</th>
							<th scope="col">Data quality</th>
							<th scope="col">
								<span className="visually-hidden">Actions</span>
							</th>
						</tr>
					</thead>
					<tbody>
						{visibleEvaluations.map((evaluation) => (
							<tr
								data-tour={
									evaluation.status === "processing"
										? "row-processing"
										: evaluation.eligibility ===
												"not_eligible"
											? "row-not-eligible"
											: undefined
								}
								key={evaluation.id}
							>
								<td>
									<span style={{ fontWeight: 600 }}>
										{evaluation.candidateName ??
											"Candidate"}
									</span>
									{evaluation.candidateEmail && (
										<span className="candidate-email">
											{evaluation.candidateEmail}
										</span>
									)}
								</td>
								<td>
									{evaluation.score !== null ? (
										<span className="score-cell">
											{evaluation.score}
											<span className="score-denominator">
												/100
											</span>
										</span>
									) : evaluation.qualityState ===
										"review_required" ? (
										<span className="muted-copy">
											Review required
										</span>
									) : evaluation.status === "complete" ||
										evaluation.status === "failed" ? (
										<span className="muted-copy">—</span>
									) : (
										<span className="pending-cell">
											<ThinkingOrb
												aria-hidden
												size={20}
												state="solving"
											/>
											Queued
										</span>
									)}
								</td>
								<td>
									<span
										className={eligibilityChipClass(
											evaluation.eligibility,
										)}
									>
										{evaluation.eligibility.replace(
											/_/g,
											" ",
										)}
									</span>
								</td>
								<td>
									<HardGateSummary
										gates={evaluation.hardGates ?? []}
									/>
								</td>
								<td>
									{evaluation.coverage !== null ? (
										<span className="coverage-cell">
											<span
												aria-hidden
												className="coverage-meter"
											>
												<span
													className="coverage-meter-fill"
													style={{
														width: `${Math.min(100, Math.max(0, evaluation.coverage))}%`,
													}}
												/>
											</span>
											{evaluation.coverage}%
										</span>
									) : (
										"—"
									)}
								</td>
								<td>
									<span className="quality-cell">
										{(
											evaluation.qualityState ?? "pending"
										).replace(/_/g, " ")}
										{(evaluation.qualityWarnings?.length ??
											0) > 0 && (
											<small>
												{evaluation.qualityWarnings
													?.length ?? 0}{" "}
												warning
												{evaluation.qualityWarnings
													?.length === 1
													? ""
													: "s"}
											</small>
										)}
									</span>
								</td>
								<td className="cell-action">
									<Button
										onClick={() => onInspect(evaluation)}
										size="sm"
										variant="outline"
									>
										Inspect
									</Button>
								</td>
							</tr>
						))}
						{visibleEvaluations.length === 0 && (
							<tr>
								<td colSpan={7}>
									{evaluations.length === 0 ? (
										<div className="empty-state">
											<FileText aria-hidden />
											<h3>No resumes evaluated yet</h3>
											<p>
												Upload resumes or invite
												candidates once criteria are
												confirmed.
											</p>
											<Button onClick={onQueue} size="sm">
												<UploadCloud />
												Queue resumes
											</Button>
										</div>
									) : (
										<p className="empty-state">
											No evaluations match the current
											filters.
										</p>
									)}
								</td>
							</tr>
						)}
					</tbody>
				</table>
			</div>
		</div>
	);
};

const HardGateSummary = ({
	gates,
}: {
	gates: Array<{ requirement: string; outcome: string }>;
}) => {
	if (gates.length === 0) {
		return <span className="muted-copy">—</span>;
	}
	const failed = gates.filter((gate) => gate.outcome === "not_met").length;
	const attention = gates.filter(
		(gate) => gate.outcome === "partial" || gate.outcome === "unknown",
	).length;
	if (failed > 0) {
		return (
			<span className="gate-chip gate-failed">
				{failed} gate{failed === 1 ? "" : "s"} failed
			</span>
		);
	}
	if (attention > 0) {
		return (
			<span className="gate-chip gate-review">
				{attention} need{attention === 1 ? "s" : ""} review
			</span>
		);
	}
	return (
		<span className="gate-chip gate-met">
			{gates.length} gate{gates.length === 1 ? "" : "s"} met
		</span>
	);
};
