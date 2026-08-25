import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { Label } from "@skillsignal/ui/components/label";
import { Textarea } from "@skillsignal/ui/components/textarea";
import { type FormEvent, useState } from "react";
import type { JobDetail, Organization } from "./client";
import { workspaceClient } from "./client";
import { overlayBackdrop, toLocalInput } from "./shared";

type CreateOrganizationDialogProps = {
	onDismiss: () => void;
	onError: (reason: unknown) => void;
	onCreated: (organization: Organization) => void;
};

export const CreateOrganizationDialog = ({
	onDismiss,
	onError,
	onCreated,
}: CreateOrganizationDialogProps) => {
	const [name, setName] = useState("");

	const createOrganization = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!name.trim()) return;
		try {
			const created = await workspaceClient.createOrganization(name);
			setName("");
			onCreated(created);
		} catch (reason) {
			onError(reason);
		}
	};

	return (
		<div
			{...overlayBackdrop({
				labelledBy: "create-org-title",
				onDismiss,
			})}
		>
			<form className="modal-panel" onSubmit={createOrganization}>
				<h3 id="create-org-title">Create organization</h3>
				<div className="form-field">
					<Label htmlFor="org-name">Organization name</Label>
					<Input
						id="org-name"
						onChange={(event) => setName(event.target.value)}
						placeholder="Acme Corp"
						required
						value={name}
					/>
				</div>
				<div className="modal-actions">
					<Button
						onClick={onDismiss}
						size="sm"
						variant="outline"
						type="button"
					>
						Cancel
					</Button>
					<Button size="sm" type="submit">
						Create
					</Button>
				</div>
			</form>
		</div>
	);
};

type CreateJobDialogProps = {
	organizationId: string;
	onDismiss: () => void;
	onError: (reason: unknown) => void;
	onCreated: (detail: JobDetail) => void;
};

export const CreateJobDialog = ({
	organizationId,
	onDismiss,
	onError,
	onCreated,
}: CreateJobDialogProps) => {
	const [title, setTitle] = useState("");
	const [description, setDescription] = useState("");
	const [descriptionFile, setDescriptionFile] = useState<File | null>(null);

	const createJob = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (
			!title.trim() ||
			!organizationId ||
			(!description.trim() && !descriptionFile)
		) {
			return;
		}
		try {
			const job = await workspaceClient.createJob(
				organizationId,
				title,
				description,
				descriptionFile,
			);
			const detail = await workspaceClient.job(job.id);
			onCreated(detail);
		} catch (reason) {
			onError(reason);
		}
	};

	return (
		<div
			{...overlayBackdrop({
				labelledBy: "create-job-title",
				onDismiss,
			})}
		>
			<form className="modal-panel" onSubmit={createJob}>
				<h3 id="create-job-title">Create role</h3>
				<div className="form-field">
					<Label htmlFor="create-job-title">Role title</Label>
					<Input
						id="create-job-title"
						onChange={(event) => setTitle(event.target.value)}
						placeholder="Senior Backend Engineer"
						required
						value={title}
					/>
				</div>
				<div className="form-field">
					<Label htmlFor="create-job-description">
						Job description
					</Label>
					<Textarea
						id="create-job-description"
						onChange={(event) => setDescription(event.target.value)}
						placeholder={
							descriptionFile
								? "Using the uploaded file. Clear it to paste instead."
								: "Paste the full description. Draft criteria are extracted automatically."
						}
						value={description}
					/>
					<Input
						accept=".pdf,.docx,.txt"
						id="create-job-description-file"
						onChange={(event) => {
							const selected =
								event.currentTarget.files?.[0] ?? null;
							setDescriptionFile(selected);
							if (selected) setDescription("");
						}}
						type="file"
					/>
					<p className="form-hint">
						Paste a description or upload a PDF, DOCX, or TXT file.
					</p>
				</div>
				<div className="modal-actions">
					<Button
						onClick={onDismiss}
						size="sm"
						variant="outline"
						type="button"
					>
						Cancel
					</Button>
					<Button size="sm" type="submit">
						Create role
					</Button>
				</div>
			</form>
		</div>
	);
};

type ApplicationWindowDialogProps = {
	job: JobDetail;
	onDismiss: () => void;
	onError: (reason: unknown) => void;
	onSaved: (detail: JobDetail) => void;
};

export const ApplicationWindowDialog = ({
	job,
	onDismiss,
	onError,
	onSaved,
}: ApplicationWindowDialogProps) => {
	const [opensAt, setOpensAt] = useState(
		toLocalInput(job.applicationOpensAt),
	);
	const [closesAt, setClosesAt] = useState(
		toLocalInput(job.applicationClosesAt),
	);

	const saveApplicationWindow = async (event: FormEvent<HTMLFormElement>) => {
		event.preventDefault();
		if (!opensAt || !closesAt) return;
		try {
			await workspaceClient.setApplicationWindow(
				job.id,
				new Date(opensAt).toISOString(),
				new Date(closesAt).toISOString(),
			);
			onSaved(await workspaceClient.job(job.id));
		} catch (reason) {
			onError(reason);
		}
	};

	return (
		<div
			{...overlayBackdrop({
				labelledBy: "window-title",
				onDismiss,
			})}
		>
			<form className="modal-panel" onSubmit={saveApplicationWindow}>
				<h3 id="window-title">Application window</h3>
				<p className="muted-copy">
					Candidates can submit resumes through invitations only while
					the window is open.
				</p>
				<div className="form-field">
					<Label htmlFor="window-opens">Opens at</Label>
					<Input
						id="window-opens"
						onChange={(event) => setOpensAt(event.target.value)}
						required
						type="datetime-local"
						value={opensAt}
					/>
				</div>
				<div className="form-field">
					<Label htmlFor="window-closes">Closes at</Label>
					<Input
						id="window-closes"
						onChange={(event) => setClosesAt(event.target.value)}
						required
						type="datetime-local"
						value={closesAt}
					/>
				</div>
				<div className="modal-actions">
					<Button
						onClick={onDismiss}
						size="sm"
						variant="outline"
						type="button"
					>
						Cancel
					</Button>
					<Button size="sm" type="submit">
						Save window
					</Button>
				</div>
			</form>
		</div>
	);
};
