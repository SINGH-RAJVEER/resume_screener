import { Document, HeadingLevel, Packer, Paragraph } from "docx";

const MAX_RENDERED_TEXT_CHARACTERS = 2000;

type Entry = Record<string, unknown>;

const mappingOf = (value: unknown): Entry =>
	typeof value === "object" && value !== null && !Array.isArray(value) ? (value as Entry) : {};

const entriesOf = (value: unknown): Entry[] =>
	Array.isArray(value) ? value.filter((item): item is Entry => typeof item === "object" && item !== null && !Array.isArray(item)) : [];

const textOf = (value: unknown): string | null => {
	if (typeof value !== "string") return null;
	const cleaned = [...value].filter((character) => character === "\t" || character === "\n" || character === "\r" || (character.codePointAt(0) ?? 0) >= 0x20).join("").trim();
	if (!cleaned) return null;
	return cleaned.slice(0, MAX_RENDERED_TEXT_CHARACTERS);
};

export const renderResumeDocx = async (facts: Readonly<Record<string, unknown>>, suggestions: readonly Entry[]): Promise<Uint8Array> => {
	const contact = mappingOf(facts["contact"]);
	const name = textOf(contact["name"]) ?? "Resume";
	const children: Paragraph[] = [new Paragraph({ text: name, heading: HeadingLevel.TITLE })];
	const contactLine = [textOf(contact["email"]), textOf(contact["phone"]), textOf(contact["location"])].filter((item): item is string => Boolean(item)).join(" · ");
	if (contactLine) children.push(new Paragraph(contactLine));

	const skills = entriesOf(facts["skills"]);
	if (skills.length) {
		children.push(new Paragraph({ text: "Skills", heading: HeadingLevel.HEADING_1 }));
		const grouped = new Map<string, string[]>();
		for (const skill of skills) {
			const canonical = textOf(skill["canonicalName"]);
			if (!canonical) continue;
			const category = textOf(skill["category"]) ?? "Other";
			grouped.set(category, [...(grouped.get(category) ?? []), canonical]);
		}
		for (const category of [...grouped.keys()].sort()) {
			children.push(new Paragraph(`${category}: ${[...(grouped.get(category) ?? [])].sort((a, b) => a.toLowerCase().localeCompare(b.toLowerCase())).join(", ")}`));
		}
	}

	const employment = entriesOf(facts["employment"]);
	if (employment.length) {
		children.push(new Paragraph({ text: "Experience", heading: HeadingLevel.HEADING_1 }));
		for (const role of employment) {
			const title = [textOf(role["title"]), textOf(role["employer"])].filter((item): item is string => Boolean(item)).join(" — ");
			const start = textOf(role["startDate"]);
			const end = textOf(role["endDate"]);
			const dates = role["isCurrent"] === true && start ? `${start} to present` : start && end ? `${start} to ${end}` : start ?? end ?? "";
			const line = title && dates ? `${title} (${dates})` : title || dates || "Role";
			children.push(new Paragraph(line));
		}
	}

	const education = entriesOf(facts["education"]);
	if (education.length) {
		children.push(new Paragraph({ text: "Education", heading: HeadingLevel.HEADING_1 }));
		for (const entry of education) {
			const parts = [textOf(entry["degree"]), textOf(entry["fieldOfStudy"]), textOf(entry["institution"])].filter((item): item is string => Boolean(item));
			if (parts.length) children.push(new Paragraph(parts.join(", ")));
		}
	}

	const certifications = entriesOf(facts["certifications"]);
	if (certifications.length) {
		children.push(new Paragraph({ text: "Certifications", heading: HeadingLevel.HEADING_1 }));
		for (const entry of certifications) {
			const parts = [textOf(entry["name"]), textOf(entry["issuer"])].filter((item): item is string => Boolean(item));
			if (parts.length) children.push(new Paragraph(parts.join(" — ")));
		}
	}

	if (suggestions.length) {
		children.push(new Paragraph({ text: "Improvement notes", heading: HeadingLevel.HEADING_1 }));
		for (const suggestion of suggestions) {
			const title = textOf(suggestion["title"]);
			const detail = textOf(suggestion["detail"]);
			const line = title && detail ? `${title}: ${detail}` : title ?? detail;
			if (line) children.push(new Paragraph({ text: line, bullet: { level: 0 } }));
		}
	}

	return new Uint8Array(await Packer.toBuffer(new Document({ sections: [{ children }] })));
};
