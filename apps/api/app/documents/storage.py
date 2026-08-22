from pathlib import Path


class LocalObjectStorage:
	def __init__(self, root: Path) -> None:
		self._root = root.resolve()

	def put(self, key: str, content: bytes) -> None:
		path = (self._root / key).resolve()
		if self._root not in path.parents:
			raise ValueError("Storage key escapes the configured root")
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_bytes(content)

	def delete(self, key: str) -> None:
		path = (self._root / key).resolve()
		if self._root not in path.parents:
			raise ValueError("Storage key escapes the configured root")
		path.unlink(missing_ok=True)
