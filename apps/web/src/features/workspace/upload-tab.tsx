import { Button } from "@skillsignal/ui/components/button";
import { Label } from "@skillsignal/ui/components/label";
import { FileUp, FolderUp, UploadCloud } from "lucide-react";
import type { FormEvent } from "react";
import { ThinkingOrb } from "thinking-orbs";

type UploadTabProps = {
	confirmed: boolean;
	isUploading: boolean;
	resumes: File[];
	uploadInputKey: number;
	appendResumes: (files: File[]) => void;
	onSubmit: (event: FormEvent<HTMLFormElement>) => void;
	onConfirmCriteria: () => void;
};

export const UploadTab = ({
	confirmed,
	isUploading,
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

		<form
			className="upload-panel"
			data-tour="upload-panel"
			onSubmit={onSubmit}
		>
			<h3>Queue resume submissions</h3>

			<div className="form-field">
				<div className="flex items-center justify-between gap-3">
					<div>
						<Label>Resume documents</Label>
						{resumes.length > 0 && (
							<p className="mt-1 text-xs text-muted-foreground">
								{resumes.length} file
								{resumes.length === 1 ? "" : "s"} selected
							</p>
						)}
					</div>

					<div className="flex items-center gap-2">
						<input
							accept=".pdf,.docx,.txt,.zip"
							className="sr-only"
							id="resume-files"
							key={uploadInputKey}
							multiple
							onChange={(event) =>
								appendResumes(
									Array.from(event.currentTarget.files ?? []),
								)
							}
							type="file"
						/>

						<Button
							aria-label="Upload resume files"
							asChild
							size="icon"
							title="Upload files"
							type="button"
							variant="outline"
						>
							<label htmlFor="resume-files">
								<FileUp className="size-4" />
							</label>
						</Button>

						<input
							{...({ webkitdirectory: "" } as Record<
								string,
								string
							>)}
							className="sr-only"
							id="resume-folder"
							key={`folder-${uploadInputKey}`}
							onChange={(event) =>
								appendResumes(
									Array.from(event.currentTarget.files ?? []),
								)
							}
							type="file"
						/>

						<Button
							aria-label="Upload resume folder"
							asChild
							size="icon"
							title="Upload folder"
							type="button"
							variant="outline"
						>
							<label htmlFor="resume-folder">
								<FolderUp className="size-4" />
							</label>
						</Button>
					</div>
				</div>

				<p className="form-hint">
					Choose PDF, DOCX, TXT, ZIP files, or an entire folder.
					Unsupported files are reported individually and candidate
					names come from the resumes.
				</p>
			</div>

			<Button
				disabled={resumes.length === 0 || !confirmed || isUploading}
				type="submit"
			>
				{isUploading ? (
					<ThinkingOrb aria-hidden size={20} state="solving" />
				) : (
					<UploadCloud />
				)}
				{isUploading
					? "Queuing resumes..."
					: `Queue ${resumes.length || "selected"} resume${resumes.length === 1 ? "" : "s"}`}
			</Button>
		</form>
	</div>
);
