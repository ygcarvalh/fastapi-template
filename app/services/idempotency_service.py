import hashlib
from datetime import UTC, datetime, timedelta

from app.models.idempotency_key import IdempotencyKey
from app.schemas.idempotency import Attempt, Claim, ClaimState, StoredResponse
from app.services.protocols import IdempotencyRepositoryProtocol
from app.services.support import prune_before


def fingerprint(attempt: Attempt) -> str:
    digest = hashlib.sha256()
    digest.update(attempt.method.encode())
    digest.update(b"\0")
    digest.update(attempt.path.encode())
    digest.update(b"\0")
    digest.update(attempt.body)
    return digest.hexdigest()


class IdempotencyService:
    def __init__(
        self,
        repo: IdempotencyRepositoryProtocol,
        *,
        in_flight_timeout: timedelta = timedelta(seconds=60),
    ) -> None:
        self._repo = repo
        self._in_flight_timeout = in_flight_timeout

    async def claim(self, attempt: Attempt) -> Claim:
        request_hash = fingerprint(attempt)
        existing = await self._repo.get(attempt.user_id, attempt.key)
        if existing is not None:
            return await self._resolve(existing, request_hash)

        entry = IdempotencyKey(
            key=attempt.key,
            user_id=attempt.user_id,
            method=attempt.method,
            path=attempt.path,
            request_hash=request_hash,
        )
        if await self._repo.claim(entry) is not None:
            return Claim(ClaimState.FRESH)

        raced = await self._repo.get(attempt.user_id, attempt.key)
        if raced is None:
            return Claim(ClaimState.IN_FLIGHT)
        return await self._resolve(raced, request_hash)

    async def complete(self, user_id: int, key: str, response: StoredResponse) -> None:
        entry = await self._repo.get(user_id, key)
        if entry is None:
            return
        await self._repo.complete(
            entry,
            status_code=response.status_code,
            body=response.body,
            content_type=response.content_type,
            completed_at=datetime.now(UTC),
        )

    async def release(self, user_id: int, key: str) -> None:
        entry = await self._repo.get(user_id, key)
        if entry is not None:
            await self._repo.release(entry)

    async def prune_batch(self, retention: timedelta, batch_size: int) -> int:
        return await prune_before(
            self._repo.delete_batch_created_before, retention, batch_size
        )

    async def _resolve(self, entry: IdempotencyKey, request_hash: str) -> Claim:
        running = entry.completed_at is None or entry.status_code is None
        if running and self._abandoned(entry):
            await self._repo.restart(entry, request_hash, datetime.now(UTC))
            return Claim(ClaimState.FRESH)
        if entry.request_hash != request_hash:
            return Claim(ClaimState.MISMATCH)
        if running or entry.status_code is None:
            return Claim(ClaimState.IN_FLIGHT)
        return Claim(
            ClaimState.REPLAY,
            StoredResponse(
                entry.status_code, entry.response_body or "", entry.content_type
            ),
        )

    def _abandoned(self, entry: IdempotencyKey) -> bool:
        started = entry.created_at
        if started is None:
            return False
        if started.tzinfo is None:
            started = started.replace(tzinfo=UTC)
        return datetime.now(UTC) - started > self._in_flight_timeout
