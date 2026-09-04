const MAX_PAGES = 100;
const MAX_EXTRACTED_CHARACTERS = 250_000;
const MAX_DOCX_DOCUMENT_XML_BYTES = 25 * 1024 * 1024;
const MAX_DOCX_PACKAGE_ENTRIES = 1_000;
const MAX_DOCX_PACKAGE_BYTES = 50 * 1024 * 1024;
const MAX_DOCX_COMPRESSION_RATIO = 100;
const MIN_RELIABLE_NON_WHITESPACE_CHARACTERS = 40;

const INSTRUCTION_LIKE_TEXT =
	/\b(?:ignore (?:all |any )?(?:previous|prior) instructions|reveal (?:the )?system prompt|give this resume (?:a )?perfect score)\b/i;
const ENGLISH_WORDS = new Set(
	`the and for with from to of on at by an is are was were be been as it its this that these those or but not have has had will would can could their our your they we you experience senior junior engineer engineering manager management developed developer development built designed led managed operated created improved reduced increased implemented delivered maintained supported education university college degree bachelor master science computer software services service platform systems system team teams project projects skills certified certification location united kingdom states corporation corp inc ltd llc group company consultant analyst specialist coordinator director head lead staff principal architect`.split(
		" ",
	),
);

export class DocumentParseError extends Error {
	constructor(message: string) {
		super(message);
		this.name = "DocumentParseError";
	}
}

export type BlockMethod = "plain_text" | "pdf_text" | "docx_xml";
export interface EvidenceBlock {
	id: string;
	page: number;
	readingOrder: number;
	text: string;
	method: BlockMethod;
	bbox: number[] | null;
}
export interface ParsedDocument {
	blocks: EvidenceBlock[];
	metadata: {
		mediaType: string;
		pageCount: number;
		blockCount: number;
		characterCount: number;
		nonWhitespaceCharacterCount: number;
	};
	quality: { state: "ready" | "review_required"; warnings: string[] };
}

export async function extractBlocks(
	content: Uint8Array,
	mediaType: string,
): Promise<ParsedDocument> {
	if (mediaType === "text/plain")
		return parsedDocument(
			paragraphBlocks([decodeText(content)], "plain_text"),
			mediaType,
			1,
		);
	if (mediaType === "application/pdf") return extractPdfBlocks(content);
	if (mediaType.endsWith("wordprocessingml.document")) {
		const paragraphs = await extractDocxParagraphs(content);
		return parsedDocument(
			paragraphBlocks(paragraphs, "docx_xml", false),
			mediaType,
			1,
		);
	}
	throw new DocumentParseError("Unsupported resume document type");
}

function decodeText(content: Uint8Array): string {
	const encoding =
		content[0] === 0xff && content[1] === 0xfe
			? "utf-16le"
			: content[0] === 0xfe && content[1] === 0xff
				? "utf-16be"
				: "utf-8";
	try {
		const text = new TextDecoder(encoding, { fatal: true }).decode(content);
		return normalizeText(text.replace(/^\ufeff/, ""));
	} catch (error) {
		if (error instanceof DocumentParseError) throw error;
		throw new DocumentParseError("Resume text encoding is not supported");
	}
}

function normalizeText(text: string, allowEmpty = false): string {
	const normalized = text
		.normalize("NFKC")
		.replaceAll("\r\n", "\n")
		.replaceAll("\r", "\n");
	if (
		[...normalized].some(
			(character) =>
				character.charCodeAt(0) < 32 &&
				character !== "\n" &&
				character !== "\t",
		)
	)
		throw new DocumentParseError(
			"Resume text contains unsupported control characters",
		);
	if (!allowEmpty && !normalized.trim())
		throw new DocumentParseError(
			"Resume text contains no extractable text",
		);
	if (normalized.length > MAX_EXTRACTED_CHARACTERS)
		throw new DocumentParseError(
			"Resume contains too much extractable text",
		);
	return normalized;
}

function paragraphBlocks(
	pages: string[],
	method: BlockMethod,
	split = true,
): EvidenceBlock[] {
	const blocks: EvidenceBlock[] = [];
	let order = 1;
	for (const [pageIndex, page] of pages.entries()) {
		const paragraphs = split ? page.split(/\n[\t ]*\n+/) : [page];
		for (const paragraph of paragraphs) {
			const text = paragraph.trim();
			if (text)
				blocks.push({
					id: `p${pageIndex + 1}-b${order}`,
					page: pageIndex + 1,
					readingOrder: order++,
					text,
					method,
					bbox: null,
				});
		}
	}
	return blocks;
}

function extractPdfBlocks(content: Uint8Array): ParsedDocument {
	const source = new TextDecoder("latin1").decode(content);
	if (!source.startsWith("%PDF-"))
		throw new DocumentParseError("Resume PDF has invalid magic bytes");
	if (!source.includes("%%EOF"))
		throw new DocumentParseError("Resume PDF could not be parsed");
	const pageCount = Math.max(
		1,
		(source.match(/\/Type\s*\/Page(?:\s|\/|>)/g) ?? []).length,
	);
	if (pageCount > MAX_PAGES)
		throw new DocumentParseError("Resume PDF exceeds 100 pages");
	const strings: string[] = [];
	for (let index = 0; index < source.length; index++) {
		if (source[index] !== "(") continue;
		let value = "";
		let depth = 1;
		for (index++; index < source.length && depth; index++) {
			const character = source[index];
			if (character === "\\") {
				value += source[++index] ?? "";
				continue;
			}
			if (character === "(") depth++;
			else if (character === ")") {
				depth--;
				if (!depth) break;
			}
			value += character;
		}
		if (depth)
			throw new DocumentParseError("Resume PDF could not be parsed");
		if (value.trim()) strings.push(value);
	}
	if (!strings.length)
		throw new DocumentParseError(
			"Scanned or image-only resume PDFs are not supported",
		);
	const pages = strings
		.join("\n")
		.split(/\f/)
		.map((page) => normalizeText(page, true));
	return parsedDocument(
		paragraphBlocks(pages, "pdf_text"),
		"application/pdf",
		pageCount,
		pageCount > pages.length ? pageCount - pages.length : 0,
	);
}

async function extractDocxParagraphs(content: Uint8Array): Promise<string[]> {
	const entries = readZipEntries(content);
	if (entries.length > MAX_DOCX_PACKAGE_ENTRIES)
		throw new DocumentParseError(
			"Resume DOCX has too many package entries",
		);
	if (entries.some((entry) => entry.encrypted))
		throw new DocumentParseError(
			"Encrypted DOCX packages are not supported",
		);
	if (
		entries.some((entry) =>
			entry.name.toLowerCase().endsWith("vbaproject.bin"),
		)
	)
		throw new DocumentParseError(
			"Macro-enabled DOCX packages are not supported",
		);
	if (
		entries.reduce((sum, entry) => sum + entry.size, 0) >
		MAX_DOCX_PACKAGE_BYTES
	)
		throw new DocumentParseError("Resume DOCX package is too large");
	if (
		entries.some(
			(entry) =>
				entry.compressedSize > 0 &&
				entry.size / entry.compressedSize > MAX_DOCX_COMPRESSION_RATIO,
		)
	)
		throw new DocumentParseError(
			"Resume DOCX has a suspicious compression ratio",
		);
	const entry = entries.find(
		(candidate) => candidate.name === "word/document.xml",
	);
	if (!entry) throw new DocumentParseError("Resume DOCX could not be parsed");
	if (entry.size > MAX_DOCX_DOCUMENT_XML_BYTES)
		throw new DocumentParseError(
			"Resume DOCX decompresses to too much content",
		);
	const document = new TextDecoder("utf-8", { fatal: true }).decode(
		await unzipEntry(content, entry),
	);
	if (/<!DOCTYPE|<!ENTITY/i.test(document))
		throw new DocumentParseError(
			"Resume DOCX contains unsupported markup declarations",
		);
	const paragraphOpen = document.match(/<w:p(?:\s[^>]*)?>/g) ?? [];
	const paragraphClose = document.match(/<\/w:p\s*>/g) ?? [];
	if (paragraphOpen.length !== paragraphClose.length)
		throw new DocumentParseError("Resume DOCX could not be parsed");
	const paragraphs = [
		...document.matchAll(/<w:p(?:\s[^>]*)?>([\s\S]*?)<\/w:p\s*>/g),
	]
		.map((match) => {
			const body = match[1] ?? "";
			if (
				(body.match(/<w:t(?:\s[^>]*)?>/g) ?? []).length !==
				(body.match(/<\/w:t\s*>/g) ?? []).length
			)
				throw new DocumentParseError("Resume DOCX could not be parsed");
			return [
				...body.matchAll(
					/<w:t(?:\s[^>]*)?>([\s\S]*?)<\/w:t\s*>|<w:tab\s*\/?>|<w:(?:br|cr)\s*\/?>/g,
				),
			]
				.map((match) =>
					match[1] === undefined
						? match[0].includes("tab")
							? "\t"
							: "\n"
						: decodeXmlText(match[1]),
				)
				.join("");
		})
		.map((text) => normalizeText(text, true))
		.filter((text) => text.trim());
	if (!paragraphs.length)
		throw new DocumentParseError(
			"Resume DOCX contains no extractable text",
		);
	return paragraphs;
}

function decodeXmlText(text: string): string {
	const entities: Record<string, string> = {
		"&amp;": "&",
		"&lt;": "<",
		"&gt;": ">",
		"&quot;": '"',
		"&apos;": "'",
	};
	return text.replace(
		/&(?:amp|lt|gt|quot|apos);/g,
		(entity) => entities[entity] ?? entity,
	);
}

interface ZipEntry {
	name: string;
	compressedSize: number;
	size: number;
	method: number;
	offset: number;
	encrypted: boolean;
}
function readZipEntries(content: Uint8Array): ZipEntry[] {
	const view = new DataView(
		content.buffer,
		content.byteOffset,
		content.byteLength,
	);
	let eocd = -1;
	for (
		let offset = content.length - 22;
		offset >= Math.max(0, content.length - 65_557);
		offset--
	)
		if (view.getUint32(offset, true) === 0x06054b50) {
			eocd = offset;
			break;
		}
	if (eocd < 0)
		throw new DocumentParseError("Resume DOCX could not be parsed");
	const count = view.getUint16(eocd + 10, true);
	const centralOffset = view.getUint32(eocd + 16, true);
	const entries: ZipEntry[] = [];
	let offset = centralOffset;
	for (let index = 0; index < count; index++) {
		if (
			offset + 46 > content.length ||
			view.getUint32(offset, true) !== 0x02014b50
		)
			throw new DocumentParseError("Resume DOCX could not be parsed");
		const flags = view.getUint16(offset + 8, true);
		const method = view.getUint16(offset + 10, true);
		const compressedSize = view.getUint32(offset + 20, true);
		const size = view.getUint32(offset + 24, true);
		const nameLength = view.getUint16(offset + 28, true);
		const extraLength = view.getUint16(offset + 30, true);
		const commentLength = view.getUint16(offset + 32, true);
		const name = new TextDecoder().decode(
			content.slice(offset + 46, offset + 46 + nameLength),
		);
		const localOffset = view.getUint32(offset + 42, true);
		entries.push({
			name,
			compressedSize,
			size,
			method,
			offset: localOffset,
			encrypted: (flags & 1) !== 0,
		});
		offset += 46 + nameLength + extraLength + commentLength;
	}
	return entries;
}

async function unzipEntry(
	content: Uint8Array,
	entry: ZipEntry,
): Promise<Uint8Array> {
	const view = new DataView(
		content.buffer,
		content.byteOffset,
		content.byteLength,
	);
	if (
		entry.offset + 30 > content.length ||
		view.getUint32(entry.offset, true) !== 0x04034b50
	)
		throw new DocumentParseError("Resume DOCX could not be parsed");
	const nameLength = view.getUint16(entry.offset + 26, true);
	const extraLength = view.getUint16(entry.offset + 28, true);
	const start = entry.offset + 30 + nameLength + extraLength;
	const compressed = content.slice(start, start + entry.compressedSize);
	try {
		if (entry.method === 0) return compressed;
		if (entry.method !== 8)
			throw new DocumentParseError(
				"Resume DOCX compression method is not supported",
			);
		const stream = new Blob([compressed])
			.stream()
			.pipeThrough(new DecompressionStream("deflate-raw"));
		return new Uint8Array(await new Response(stream).arrayBuffer());
	} catch (error) {
		if (error instanceof DocumentParseError) throw error;
		throw new DocumentParseError("Resume DOCX could not be parsed");
	}
}

function parsedDocument(
	blocks: EvidenceBlock[],
	mediaType: string,
	pageCount: number,
	emptyPageCount = 0,
): ParsedDocument {
	const joined = blocks.map((block) => block.text).join("\n\n");
	if (!joined.trim())
		throw new DocumentParseError("Resume contains no extractable text");
	if (joined.length > MAX_EXTRACTED_CHARACTERS)
		throw new DocumentParseError(
			"Resume contains too much extractable text",
		);
	rejectNonEnglishText(joined);
	const warnings: string[] = [];
	const nonWhitespace = [...joined].filter(
		(character) => !/\s/u.test(character),
	).length;
	if (nonWhitespace < MIN_RELIABLE_NON_WHITESPACE_CHARACTERS)
		warnings.push("Document contains very little extractable text");
	if (emptyPageCount)
		warnings.push(
			`${emptyPageCount} of ${pageCount} ${pageCount === 1 ? "page" : "pages"} contained no extractable text`,
		);
	const normalized = blocks.map((block) =>
		block.text.replace(/\s+/g, " ").trim().toLowerCase(),
	);
	const duplicateCount = normalized.length - new Set(normalized).size;
	if (normalized.length >= 2 && duplicateCount / normalized.length >= 0.5)
		warnings.push(
			"Extracted text contains repeated blocks that may be duplicated",
		);
	if (INSTRUCTION_LIKE_TEXT.test(joined))
		warnings.push(
			"Document contains instruction-like text that requires review",
		);
	return {
		blocks,
		metadata: {
			mediaType,
			pageCount,
			blockCount: blocks.length,
			characterCount: joined.length,
			nonWhitespaceCharacterCount: nonWhitespace,
		},
		quality: {
			state: warnings.length ? "review_required" : "ready",
			warnings,
		},
	};
}

function rejectNonEnglishText(text: string): void {
	const letters = [...text].filter((character) => /\p{L}/u.test(character));
	if (
		letters.length &&
		letters.filter((character) => (character.codePointAt(0) ?? 0) > 0x24f)
			.length /
			letters.length >
			0.25
	)
		throw new DocumentParseError(
			"Resume text uses an unsupported writing system",
		);
	const tokens = text.match(/[A-Za-z]{2,}/g) ?? [];
	if (
		tokens.length >= 15 &&
		!tokens.some((token) => ENGLISH_WORDS.has(token.toLowerCase()))
	)
		throw new DocumentParseError(
			"Resume text does not appear to be in English",
		);
}
