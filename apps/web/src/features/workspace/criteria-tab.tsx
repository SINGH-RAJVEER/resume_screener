import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { CheckCircle2, Plus } from "lucide-react";
import { ThinkingOrb } from "thinking-orbs";
import type { JobDetail, Requirement } from "./client";

const formatRequirementLabel = (value?: string) =>
	value ? value.replaceAll("_", " ") : "manual criterion";

type CriteriaTabProps = {
	requirements: Requirement[];
	confirmed: boolean;
	canConfirm: boolean;
	isConfirming: boolean;
	draftStatus: JobDetail["draftStatus"];
	draftError: string | null;
	draftWarnings: string[];
	draftDegraded: boolean;
	onChange: (
		index: number,
		patch: Partial<Pick<Requirement, "normalizedText" | "kind" | "weight">>,
	) => void;
	onAdd: () => void;
	onConfirm: () => void;
};

export const CriteriaTab = ({
	requirements,
	confirmed,
	canConfirm,
	isConfirming,
	draftStatus,
	draftError,
	draftWarnings,
	draftDegraded,
	onChange,
	onAdd,
	onConfirm,
}: CriteriaTabProps) => (
	<div className="workspace-stage-gap" data-tour="tab-criteria">
		<p className="criterion-note">
			Review every extracted criterion against its source. Only
			resume-evidence criteria can enter automated scoring. Hard gates
			remain a recruiter decision and only an evidenced failure can make
			an evaluation ineligible.
		</p>
		{draftStatus === "processing" && (
			<div className="criterion-processing" role="status">
				<ThinkingOrb aria-hidden size={20} state="solving" />
				Compiling requirements and checking source evidence...
			</div>
		)}
		{draftStatus === "failed" && (
			<p className="criterion-warning" role="alert">
				{draftError ??
					"The job description could not be processed. Upload a clearer digital document."}
			</p>
		)}
		{draftDegraded && (
			<p className="criterion-warning">
				Model extraction was unavailable. Review the deterministic draft
				carefully.
			</p>
		)}
		{draftWarnings.length > 0 && (
			<ul className="criterion-warnings">
				{draftWarnings.map((warning) => (
					<li key={warning}>{warning}</li>
				))}
			</ul>
		)}
		<div className="criterion-list">
			{requirements.map((requirement, index) => (
				<div className="criterion-row" key={requirement.stableId}>
					<span className="criterion-index">
						{(index + 1).toString().padStart(2, "0")}
					</span>
					<div className="criterion-content">
						<Input
							aria-label={`Requirement ${index + 1} statement`}
							className="criterion-text"
							onChange={(event) =>
								onChange(index, {
									normalizedText: event.target.value,
								})
							}
							placeholder="Requirement statement..."
							value={requirement.normalizedText ?? ""}
						/>
						<div className="criterion-metadata">
							<span>
								{formatRequirementLabel(requirement.category)}
							</span>
							<span>
								{formatRequirementLabel(
									requirement.assessability,
								)}
							</span>
							{requirement.predicate?.operator === "any_of" && (
								<span>alternative paths</span>
							)}
							{requirement.confidence !== undefined && (
								<span>
									{Math.round(requirement.confidence * 100)}%
									extraction confidence
								</span>
							)}
						</div>
						{(requirement.evidence ??
							requirement.sourceEvidence)?.[0] && (
							<blockquote className="criterion-source">
								"
								{
									(requirement.evidence ??
										requirement.sourceEvidence)?.[0]?.quote
								}
								"
							</blockquote>
						)}
					</div>
					<div className="criterion-kind">
						<select
							aria-label={`Requirement ${index + 1} kind`}
							onChange={(event) =>
								onChange(index, {
									kind: event.target
										.value as Requirement["kind"],
								})
							}
							value={requirement.kind}
						>
							<option value="required">Required</option>
							<option value="preferred">Preferred</option>
							<option
								disabled={
									requirement.assessability !==
									"resume_evidence"
								}
								value="hard_gate"
							>
								Hard gate
							</option>
							<option value="ignored">Ignored</option>
						</select>
						<Input
							aria-label={`Requirement ${index + 1} weight`}
							className="weight-input"
							max={10}
							min={1}
							onChange={(event) =>
								onChange(index, {
									weight: Number(event.target.value),
								})
							}
							title="Weight (1 to 10)"
							type="number"
							value={requirement.weight}
						/>
					</div>
				</div>
			))}
		</div>
		<div className="criteria-actions">
			<Button onClick={onAdd} size="sm" variant="outline">
				<Plus />
				Add criterion
			</Button>
			<Button
				disabled={!canConfirm || isConfirming}
				onClick={onConfirm}
				size="sm"
			>
				{isConfirming ? (
					<ThinkingOrb aria-hidden size={20} state="solving" />
				) : (
					<CheckCircle2 />
				)}
				{isConfirming
					? "Confirming..."
					: confirmed
						? "Confirm new version"
						: "Confirm requirements"}
			</Button>
		</div>
	</div>
);
