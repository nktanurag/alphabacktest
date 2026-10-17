import shutil
from pathlib import Path

from . import config


class LocalStorage:
    """Files on disk under a root folder. Keys look like an S3 object path so a bucket can replace this."""

    def __init__(self, root: Path | None = None):
        self.root = root or config.storage_dir()

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if self.root not in path.parents:
            raise ValueError("bad storage key")
        return path

    def put(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def delete_prefix(self, prefix: str) -> None:
        shutil.rmtree(self._path(prefix), ignore_errors=True)


def document_prefix(user_id: int, document_id: int) -> str:
    return f"users/{user_id}/documents/{document_id}"


def get_storage() -> LocalStorage:
    return LocalStorage()
