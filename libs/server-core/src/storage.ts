import { join, resolve } from "node:path";

export class LocalObjectStorage {
	private readonly root: string;

	constructor(root: string) {
		this.root = resolve(root);
	}

	private resolve(key: string): string {
		const target = resolve(join(this.root, key));
		if (!target.startsWith(`${this.root}/`)) throw new Error("Storage key escapes the configured root");
		return target;
	}

	async put(key: string, content: Uint8Array): Promise<void> {
		const target = this.resolve(key);
		await Bun.write(target, content);
	}

	async get(key: string): Promise<Uint8Array> {
		const file = Bun.file(this.resolve(key));
		if (!(await file.exists())) throw new Error("Stored object is unavailable");
		return new Uint8Array(await file.arrayBuffer());
	}

	async delete(key: string): Promise<void> {
		const { unlink } = await import("node:fs/promises");
		try {
			await unlink(this.resolve(key));
		} catch (cause) {
			if ((cause as NodeJS.ErrnoException).code !== "ENOENT") throw cause;
		}
	}

	exists(key: string): Promise<boolean> {
		return Bun.file(this.resolve(key)).exists();
	}
}
