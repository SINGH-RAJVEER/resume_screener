import { Button } from "@skillsignal/ui/components/button";
import { Input } from "@skillsignal/ui/components/input";
import { ArrowDown, ArrowUp, Download, X } from "lucide-react";
import { useState } from "react";
import { EXPORT_COLUMNS, type ExportColumn, workspaceClient } from "./client";
import { overlayBackdrop } from "./shared";

type ExportDialogProps = {
	jobId: string;
	onDismiss: () => void;
	onError: (reason: unknown) => void;
};

export const ExportDialog = ({
	jobId,
	onDismiss,
	onError,
}: ExportDialogProps) => {
	const [selection, setSelection] = useState<ExportColumn[]>([
		...EXPORT_COLUMNS,
	]);
	const [labels, setLabels] = useState<Partial<Record<ExportColumn, string>>>(
		{},
	);
	const [isExporting, setIsExporting] = useState(false);

	const moveColumn = (column: ExportColumn, delta: number) => {
		setSelection((current) => {
			const index = current.indexOf(column);
			const target = index + delta;
			if (index < 0 || target < 0 || target >= current.length) {
				return current;
			}
			const next = [...current];
			next.splice(index, 1);
			next.splice(target, 0, column);
			return next;
		});
	};

	const exportCsv = async () => {
		if (isExporting) return;
		setIsExporting(true);
		try {
			await workspaceClient.exportEvaluationsCsv(jobId, {
				columns: selection,
				labels: selection.map(
					(column) => labels[column]?.trim() || column,
				),
			});
			onDismiss();
		} catch (reason) {
			onError(reason);
		} finally {
			setIsExporting(false);
		}
	};

	return (
		<div
			{...overlayBackdrop({
				labelledBy: "export-title",
				onDismiss,
			})}
		>
			<div className="modal-panel" data-tour="export-dialog">
				<h3 id="export-title">Export CSV</h3>
				<p className="muted-copy">
					Choose, reorder, and rename the exported columns.
				</p>
				<ul className="export-columns">
					{EXPORT_COLUMNS.filter((column) =>
						selection.includes(column),
					).map((column, index) => (
						<li className="export-column-row" key={column}>
							<span className="export-column-index">
								{index + 1}
							</span>
							<Input
								aria-label={`Rename ${column}`}
								onChange={(event) =>
									setLabels((current) => ({
										...current,
										[column]: event.target.value,
									}))
								}
								placeholder={column}
								value={labels[column] ?? ""}
							/>
							<Button
								aria-label={`Move ${column} up`}
								disabled={index === 0}
								onClick={() => moveColumn(column, -1)}
								size="icon-xs"
								variant="ghost"
							>
								<ArrowUp />
							</Button>
							<Button
								aria-label={`Move ${column} down`}
								disabled={index === selection.length - 1}
								onClick={() => moveColumn(column, 1)}
								size="icon-xs"
								variant="ghost"
							>
								<ArrowDown />
							</Button>
							<Button
								aria-label={`Remove ${column}`}
								onClick={() =>
									setSelection((current) =>
										current.filter(
											(selected) => selected !== column,
										),
									)
								}
								size="icon-xs"
								variant="ghost"
							>
								<X />
							</Button>
						</li>
					))}
				</ul>
				{EXPORT_COLUMNS.filter((column) => !selection.includes(column))
					.length > 0 && (
					<select
						aria-label="Add export column"
						className="workspace-filter-select"
						onChange={(event) => {
							const value = event.target.value as ExportColumn;
							if (value) {
								setSelection((current) => [...current, value]);
							}
							event.target.value = "";
						}}
						value=""
					>
						<option value="">Add column...</option>
						{EXPORT_COLUMNS.filter(
							(column) => !selection.includes(column),
						).map((column) => (
							<option key={column} value={column}>
								{column}
							</option>
						))}
					</select>
				)}
				<div className="modal-actions">
					<Button
						onClick={onDismiss}
						size="sm"
						type="button"
						variant="outline"
					>
						Cancel
					</Button>
					<Button
						disabled={selection.length === 0 || isExporting}
						onClick={() => void exportCsv()}
						size="sm"
					>
						<Download />
						{isExporting ? "Exporting..." : "Export"}
					</Button>
				</div>
			</div>
		</div>
	);
};
