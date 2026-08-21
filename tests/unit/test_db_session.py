from app.db.session import dispose_engine, get_engine, get_session_factory
from app.main import app, lifespan


async def test_get_engine_reuses_a_single_engine() -> None:
    await dispose_engine()
    try:
        assert get_engine() is get_engine()
    finally:
        await dispose_engine()


async def test_session_factory_is_bound_to_the_shared_engine() -> None:
    await dispose_engine()
    try:
        assert get_session_factory().kw["bind"] is get_engine()
    finally:
        await dispose_engine()


async def test_lifespan_releases_the_engine_on_shutdown() -> None:
    await dispose_engine()
    engine_before_shutdown = get_engine()

    async with lifespan(app):
        pass

    try:
        assert get_engine() is not engine_before_shutdown
    finally:
        await dispose_engine()
