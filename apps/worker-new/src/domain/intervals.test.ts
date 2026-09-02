import { describe, expect, test } from "bun:test";
import { employmentIntervals, monthIndex } from "./intervals.ts";

describe("employment intervals", () => {
	test("merges overlapping employment and counts overlap pairs", () => {
		const result = employmentIntervals([{ startDate: "2020-01", endDate: "2021-01" }, { startDate: "2020-06", endDate: "2022-01" }]);
		expect(result.totalMonths).toBe(24);
		expect(result.overlapCount).toBe(1);
	});
	test("uses UTC reference month for current roles", () => {
		expect(employmentIntervals([{ startDate: "2024", isCurrent: true }], new Date("2025-03-15T00:00:00Z")).totalMonths).toBe(14);
		expect(monthIndex("2024-13")).toBeNull();
	});
});
