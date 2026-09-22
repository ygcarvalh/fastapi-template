import asyncio
from collections.abc import Callable

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session as SyncSession


# Fires exactly one of on_commit/on_rollback, once, when this session's
# current transaction resolves — never both, and never for a SAVEPOINT
# (nested) outcome, since that can still be undone or superseded by the
# real outer commit/rollback later. Both hooks are registered as a pair so
# whichever one the session actually fires next retires the pair together;
# otherwise the one that didn't match would linger on the session and could
# misfire against a later, unrelated transaction sharing the same session.
def run_after_outcome(
    session: AsyncSession,
    *,
    on_commit: Callable[[], None] | None = None,
    on_rollback: Callable[[], None] | None = None,
) -> None:
    sync_session = session.sync_session
    retired = False

    def _on_commit(sync: SyncSession) -> None:
        nonlocal retired
        if retired or sync.in_nested_transaction():
            return
        retired = True
        _deregister(sync_session, _on_commit, _on_rollback)
        if on_commit is not None:
            on_commit()

    def _on_rollback(sync: SyncSession) -> None:
        nonlocal retired
        if retired or sync.in_nested_transaction():
            return
        retired = True
        _deregister(sync_session, _on_commit, _on_rollback)
        if on_rollback is not None:
            on_rollback()

    event.listen(sync_session, "after_commit", _on_commit)
    event.listen(sync_session, "after_rollback", _on_rollback)


def _deregister(
    sync_session: SyncSession,
    on_commit: Callable[[SyncSession], None],
    on_rollback: Callable[[SyncSession], None],
) -> None:
    def _remove() -> None:
        event.remove(sync_session, "after_commit", on_commit)
        event.remove(sync_session, "after_rollback", on_rollback)

    # `event.remove` must not run while SQLAlchemy is still iterating the
    # listener deque for this very dispatch (it raises "deque mutated during
    # iteration"), so the removal is deferred to the next loop iteration,
    # once the dispatch that invoked this listener has unwound.
    asyncio.get_running_loop().call_soon(_remove)
