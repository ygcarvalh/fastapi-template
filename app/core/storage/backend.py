from collections.abc import AsyncIterator
from typing import NamedTuple, Protocol


class StoredFile(NamedTuple):
    key: str
    size_bytes: int


class Storage(Protocol):
    async def save(self, key: str, chunks: AsyncIterator[bytes]) -> StoredFile: ...

    def open(self, key: str) -> AsyncIterator[bytes]: ...

    async def delete(self, key: str) -> None: ...
