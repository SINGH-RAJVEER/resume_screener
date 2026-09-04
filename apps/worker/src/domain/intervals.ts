export interface MonthInterval {
	readonly start: number;
	readonly end: number;
}

export interface EmploymentIntervals {
	readonly valid: readonly MonthInterval[];
	readonly merged: readonly MonthInterval[];
	readonly overlapCount: number;
	readonly totalMonths: number;
}

export function monthIndex(value: unknown): number | null {
	if (typeof value !== "string") return null;
	const parts = value.split("-");
	const year = Number(parts[0]);
	const month = parts.length > 1 ? Number(parts[1]) : 1;
	if (!Number.isInteger(year) || !Number.isInteger(month) || month < 1 || month > 12) return null;
	return year * 12 + month;
}

export function employmentIntervals(entries: unknown, now = new Date()): EmploymentIntervals {
	const valid: MonthInterval[] = [];
	const currentMonth = now.getUTCFullYear() * 12 + now.getUTCMonth() + 1;
	if (Array.isArray(entries)) {
		for (const item of entries) {
			if (!isRecord(item)) continue;
			const start = monthIndex(item["startDate"]);
			let end = monthIndex(item["endDate"]);
			if (end === null && item["isCurrent"] === true) end = currentMonth;
			if (start === null || end === null || end < start) continue;
			valid.push({ start, end });
		}
	}
	const merged = mergeIntervals(valid);
	let overlapCount = 0;
	for (let index = 0; index < valid.length; index += 1) {
		const left = valid[index];
		if (!left) continue;
		for (const right of valid.slice(index + 1)) {
			if (left.start <= right.end && right.start <= left.end) overlapCount += 1;
		}
	}
	return { valid, merged, overlapCount, totalMonths: merged.reduce((sum, item) => sum + Math.max(0, item.end - item.start), 0) };
}

function mergeIntervals(intervals: readonly MonthInterval[]): MonthInterval[] {
	const ordered = [...intervals].sort((left, right) => left.start - right.start || left.end - right.end);
	const merged: MonthInterval[] = [];
	for (const interval of ordered) {
		const previous = merged.at(-1);
		if (previous && interval.start <= previous.end) {
			merged[merged.length - 1] = { start: previous.start, end: Math.max(previous.end, interval.end) };
		} else {
			merged.push(interval);
		}
	}
	return merged;
}

function isRecord(value: unknown): value is Record<string, unknown> {
	return typeof value === "object" && value !== null && !Array.isArray(value);
}
