from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from app.core.storage.local import LocalStorage


def _stored_names(root: Path) -> list[str]:
    return sorted(entry.name for entry in root.iterdir())


async def _chunks(*parts: bytes) -> AsyncIterator[bytes]:
    for part in parts:
        yield part


async def test_a_saved_file_reports_what_it_wrote(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)

    stored = await storage.save("key-1", _chunks(b"hello ", b"world"))

    assert stored.key == "key-1"
    assert stored.size_bytes == 11


async def test_what_went_in_comes_back_out(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    await storage.save("key-1", _chunks(b"hello ", b"world"))

    read = b"".join([chunk async for chunk in storage.open("key-1")])

    assert read == b"hello world"


async def test_a_deleted_file_leaves_nothing_behind(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path)
    await storage.save("key-1", _chunks(b"data"))

    await storage.delete("key-1")

    assert _stored_names(tmp_path) == []


async def test_deleting_a_key_that_was_never_stored_is_quiet(tmp_path: Path) -> None:
    await LocalStorage(tmp_path).delete("never-stored")


@pytest.mark.parametrize("key", ["../escape", "nested/../../escape", "/etc/passwd"])
async def test_a_key_that_climbs_out_of_the_root_is_refused(
    tmp_path: Path, key: str
) -> None:
    storage = LocalStorage(tmp_path / "root")

    with pytest.raises(ValueError):
        await storage.save(key, _chunks(b"data"))


async def test_the_root_is_created_on_the_first_write(tmp_path: Path) -> None:
    storage = LocalStorage(tmp_path / "uploads")

    await storage.save("key-1", _chunks(b"data"))

    assert (tmp_path / "uploads" / "key-1").read_bytes() == b"data"
