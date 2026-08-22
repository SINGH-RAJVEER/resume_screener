from pathlib import Path


class LocalObjectStorage:
	def __init__(self, root: Path) -> None:
		self._root = root.resolve()

	def put(self, key: str, content: bytes) -> None:
		path = self._path(key)
		path.parent.mkdir(parents=True, exist_ok=True)
		path.write_bytes(content)

	def get(self, key: str) -> bytes:
		return self._path(key).read_bytes()

	def delete(self, key: str) -> None:
		self._path(key).unlink(missing_ok=True)

	def _path(self, key: str) -> Path:
		path = (self._root / key).resolve()
		if self._root not in path.parents:
			raise ValueError("Storage key escapes the configured root")
		return path
