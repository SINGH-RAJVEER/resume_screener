import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { UploadCloud } from "lucide-react";
import type { FormEvent } from "react";

type UploadTabProps = {
	confirmed: boolean;
	resumes: File[];
	uploadInputKey: number;
	appendResumes: (files: File[]) => void;
	onSubmit: (event: FormEvent<HTMLFormElement>) => void;
	onConfirmCriteria: () => void;
};

export const UploadTab = ({
	confirmed,
	resumes,
	uploadInputKey,
	appendResumes,
	onSubmit,
	onConfirmCriteria,
}: UploadTabProps) => (
	<div className="workspace-stage-gap">
		{!confirmed && (
			<div className="upload-warning">
				Criteria are not confirmed yet.{" "}
				<button
					className="link-button"
					onClick={onConfirmCriteria}
					type="button"
				>
					Confirm criteria first
				</button>{" "}
				so uploads are scored against a locked version.
			</div>
		)}
		<form className="upload-panel" onSubmit={onSubmit}>
			<h3>Queue resume submissions</h3>
			<div className="form-field">
				<Label htmlFor="resume-files">Resume documents or ZIP</Label>
				<Input
					accept=".pdf,.docx,.txt,.zip"
					id="resume-files"
					key={uploadInputKey}
					multiple
					onChange={(event) =>
						appendResumes(
							Array.from(event.currentTarget.files ?? []),
						)
					}
					required
					type="file"
				/>
				<Input
					{...({ webkitdirectory: "" } as Record<string, string>)}
					id="resume-folder"
					key={`folder-${uploadInputKey}`}
					onChange={(event) =>
						appendResumes(
							Array.from(event.currentTarget.files ?? []),
						)
					}
					type="file"
				/>
				<p className="form-hint">
					Choose multiple PDF, DOCX, or TXT files, select a whole
					folder, or add ZIP archives. Unsupported files are reported
					individually and candidate names come from the resumes.
				</p>
			</div>
			<Button disabled={resumes.length === 0 || !confirmed} type="submit">
				<UploadCloud />
				Queue {resumes.length || "selected"} resume
				{resumes.length === 1 ? "" : "s"}
			</Button>
		</form>
	</div>
);
