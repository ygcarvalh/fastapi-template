from datetime import timedelta

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import AuthError
from app.core.security import decode_access_token
from app.db.session import get_session_factory
from app.repositories.idempotency_repo import IdempotencyRepository
from app.schemas.idempotency import Attempt, Claim, StoredResponse
from app.services.idempotency_service import IdempotencyService

BEARER_PREFIX = "bearer "


def caller_of(request: Request) -> int | None:
    header = request.headers.get("authorization", "")
    if not header.lower().startswith(BEARER_PREFIX):
        return None
    try:
        claims = decode_access_token(header[len(BEARER_PREFIX) :].strip())
    except AuthError:
        return None
    if claims.impersonator is not None:
        return None
    try:
        return int(claims.subject)
    except ValueError:
        return None


# Only construction site for IdempotencyService, unlike PasswordResetService/
# RequestLogService — no drift risk to guard against, so no build_* split.
def _service(session: AsyncSession) -> IdempotencyService:
    return IdempotencyService(
        IdempotencyRepository(session),
        in_flight_timeout=timedelta(
            seconds=get_settings().idempotency_in_flight_timeout_seconds
        ),
    )


class DatabaseIdempotencyStore:
    async def claim(self, attempt: Attempt) -> Claim:
        async with get_session_factory()() as session:
            claim = await _service(session).claim(attempt)
            await session.commit()
            return claim

    async def complete(self, user_id: int, key: str, response: StoredResponse) -> None:
        async with get_session_factory()() as session:
            await _service(session).complete(user_id, key, response)
            await session.commit()

    async def release(self, user_id: int, key: str) -> None:
        async with get_session_factory()() as session:
            await _service(session).release(user_id, key)
            await session.commit()
