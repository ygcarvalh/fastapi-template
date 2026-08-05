import asyncio
import os
import subprocess
import sys
from collections.abc import AsyncGenerator
from urllib.parse import urlsplit, urlunsplit

import pytest_asyncio
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection, text
from sqlalchemy.ext.asyncio import create_async_engine

from app import models as _models  # noqa: F401
from app.core.config import get_settings
from app.db.base import Base

DRIFT_DATABASE = "fastapi_db_drift"
DROP_DRIFT_DATABASE = f'DROP DATABASE IF EXISTS "{DRIFT_DATABASE}"'
CREATE_DRIFT_DATABASE = f'CREATE DATABASE "{DRIFT_DATABASE}"'


def _with_database(url: str, database: str) -> str:
    parts = urlsplit(url)
    return urlunsplit(parts._replace(path=f"/{database}"))


def _require_test_database_url() -> str:
    url = get_settings().test_database_url
    if url is None:
        raise RuntimeError("TEST_DATABASE_URL is required to run the migration check")
    return url


def _upgrade_to_head(database_url: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env={**os.environ, "DATABASE_URL": database_url},
        check=True,
        capture_output=True,
    )


@pytest_asyncio.fixture
async def migrated_database_url() -> AsyncGenerator[str]:
    base_url = _require_test_database_url()
    drift_url = _with_database(base_url, DRIFT_DATABASE)
    admin = create_async_engine(
        _with_database(base_url, "postgres"), isolation_level="AUTOCOMMIT"
    )

    async with admin.connect() as connection:
        await connection.execute(text(DROP_DRIFT_DATABASE))
        await connection.execute(text(CREATE_DRIFT_DATABASE))

    await asyncio.to_thread(_upgrade_to_head, drift_url)

    yield drift_url

    async with admin.connect() as connection:
        await connection.execute(text(DROP_DRIFT_DATABASE))
    await admin.dispose()


def _differences(connection: Connection) -> list[tuple[object, ...]]:
    context = MigrationContext.configure(connection)
    return list(compare_metadata(context, Base.metadata))


async def test_migrations_match_the_models(migrated_database_url: str) -> None:
    engine = create_async_engine(migrated_database_url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(_differences)
    finally:
        await engine.dispose()

    assert differences == []
