import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from app.core.storage.backend import StoredFile

READ_CHUNK_BYTES = 64 * 1024


class LocalStorage:
    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)

    async def save(self, key: str, chunks: AsyncIterator[bytes]) -> StoredFile:
        path = self._path(key)
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        size = 0
        with path.open("wb") as handle:
            async for chunk in chunks:
                size += len(chunk)
                await asyncio.to_thread(handle.write, chunk)
        return StoredFile(key, size)

    async def open(self, key: str) -> AsyncIterator[bytes]:
        path = self._path(key)
        with path.open("rb") as handle:
            while chunk := await asyncio.to_thread(handle.read, READ_CHUNK_BYTES):
                yield chunk

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._path(key).unlink, True)

    def _path(self, key: str) -> Path:
        candidate = (self._root / key).resolve()
        root = self._root.resolve()
        if not candidate.is_relative_to(root):
            raise ValueError("a storage key must stay inside the storage root")
        return candidate
