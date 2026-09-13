import hashlib
from datetime import UTC, datetime, timedelta

from app.models.idempotency_key import IdempotencyKey
from app.schemas.idempotency import Attempt, Claim, ClaimState, StoredResponse
from app.services.protocols import IdempotencyRepositoryProtocol


def fingerprint(attempt: Attempt) -> str:
    digest = hashlib.sha256()
    digest.update(attempt.method.encode())
    digest.update(b"\0")
    digest.update(attempt.path.encode())
    digest.update(b"\0")
    digest.update(attempt.body)
    return digest.hexdigest()


class IdempotencyService:
    def __init__(self, repo: IdempotencyRepositoryProtocol) -> None:
        self._repo = repo

    async def claim(self, attempt: Attempt) -> Claim:
        request_hash = fingerprint(attempt)
        existing = await self._repo.get(attempt.user_id, attempt.key)
        if existing is not None:
            return self._judge(existing, request_hash)

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
        return self._judge(raced, request_hash)

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
        return await self._repo.delete_batch_created_before(
            datetime.now(UTC) - retention, batch_size
        )

    @staticmethod
    def _judge(entry: IdempotencyKey, request_hash: str) -> Claim:
        if entry.request_hash != request_hash:
            return Claim(ClaimState.MISMATCH)
        if entry.completed_at is None or entry.status_code is None:
            return Claim(ClaimState.IN_FLIGHT)
        return Claim(
            ClaimState.REPLAY,
            StoredResponse(
                entry.status_code, entry.response_body or "", entry.content_type
            ),
        )
