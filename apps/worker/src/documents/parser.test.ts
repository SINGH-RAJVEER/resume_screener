import { describe, expect, test } from "bun:test";
import { DocumentParseError, extractBlocks } from "./parser.ts";

describe("document parser", () => {
	test("normalizes TXT and preserves paragraph evidence", async () => {
		const parsed = await extractBlocks(
			new TextEncoder().encode(
				"Ada Lovelace\r\nada@example.com\r\n\r\nExperience\r\nBuilt Python services.",
			),
			"text/plain",
		);
		expect(parsed.blocks.map((block) => block.text)).toEqual([
			"Ada Lovelace\nada@example.com",
			"Experience\nBuilt Python services.",
		]);
		expect(parsed.quality.state).toBe("ready");
	});

	test("rejects empty, binary, oversized, and unsupported TXT safely", async () => {
		for (const content of [" \n", "Ada\0Lovelace"])
			await expect(
				extractBlocks(new TextEncoder().encode(content), "text/plain"),
			).rejects.toBeInstanceOf(DocumentParseError);
		await expect(
			extractBlocks(new Uint8Array(250_001).fill(97), "text/plain"),
		).rejects.toThrow("too much extractable text");
		await expect(
			extractBlocks(new Uint8Array(), "application/rtf"),
		).rejects.toThrow("Unsupported");
	});

	test("requires a valid PDF signature and extractable text", async () => {
		await expect(
			extractBlocks(
				new TextEncoder().encode("not pdf"),
				"application/pdf",
			),
		).rejects.toThrow("magic bytes");
		await expect(
			extractBlocks(
				new TextEncoder().encode("%PDF-1.7\n%%EOF"),
				"application/pdf",
			),
		).rejects.toThrow("image-only");
		const pdf = new TextEncoder().encode(
			"%PDF-1.7\n1 0 obj /Type /Page (Ada Lovelace Python engineer) Tj endobj\n%%EOF",
		);
		const parsed = await extractBlocks(pdf, "application/pdf");
		expect(parsed.blocks[0]?.text).toContain("Ada Lovelace");
	});

	test("reads the main document part from a valid stored DOCX ZIP", async () => {
		const xml =
			'<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>Ada Lovelace</w:t></w:r></w:p></w:body></w:document>';
		const parsed = await extractBlocks(
			storedZip("word/document.xml", xml),
			"application/vnd.openxmlformats-officedocument.wordprocessingml.document",
		);
		expect(parsed.blocks[0]?.text).toBe("Ada Lovelace");
	});
});

function storedZip(name: string, value: string): Uint8Array {
	const nameBytes = new TextEncoder().encode(name);
	const valueBytes = new TextEncoder().encode(value);
	const local = new Uint8Array(30 + nameBytes.length + valueBytes.length);
	const central = new Uint8Array(46 + nameBytes.length);
	const localView = new DataView(local.buffer);
	const centralView = new DataView(central.buffer);
	localView.setUint32(0, 0x04034b50, true);
	localView.setUint16(8, 0, true);
	localView.setUint32(18, valueBytes.length, true);
	localView.setUint32(22, valueBytes.length, true);
	localView.setUint16(26, nameBytes.length, true);
	local.set(nameBytes, 30);
	local.set(valueBytes, 30 + nameBytes.length);
	centralView.setUint32(0, 0x02014b50, true);
	centralView.setUint16(8, 0, true);
	centralView.setUint32(20, valueBytes.length, true);
	centralView.setUint32(24, valueBytes.length, true);
	centralView.setUint16(28, nameBytes.length, true);
	centralView.setUint32(42, 0, true);
	central.set(nameBytes, 46);
	const end = new Uint8Array(22);
	const endView = new DataView(end.buffer);
	endView.setUint32(0, 0x06054b50, true);
	endView.setUint16(8, 1, true);
	endView.setUint16(10, 1, true);
	endView.setUint32(12, central.length, true);
	endView.setUint32(16, local.length, true);
	return join(local, central, end);
}

function join(...parts: Uint8Array[]): Uint8Array {
	const result = new Uint8Array(
		parts.reduce((total, part) => total + part.length, 0),
	);
	let offset = 0;
	for (const part of parts) {
		result.set(part, offset);
		offset += part.length;
	}
	return result;
}
