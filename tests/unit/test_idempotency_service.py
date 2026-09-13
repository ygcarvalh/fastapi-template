from datetime import UTC, datetime, timedelta

from app.models.idempotency_key import IdempotencyKey
from app.schemas.idempotency import Attempt, ClaimState, StoredResponse
from app.services.idempotency_service import IdempotencyService, fingerprint
from tests.unit.fakes import FakeIdempotencyRepository

USER_ID = 7
KEY = "key-001"
CREATED = StoredResponse(201, '{"id":1}', "application/json")


def _attempt(body: bytes = b'{"title":"one"}', path: str = "/api/v1/items") -> Attempt:
    return Attempt(USER_ID, KEY, "POST", path, body)


async def test_a_key_nobody_used_is_fresh() -> None:
    service = IdempotencyService(FakeIdempotencyRepository())

    assert (await service.claim(_attempt())).state is ClaimState.FRESH


async def test_a_second_attempt_before_the_first_finished_is_in_flight() -> None:
    service = IdempotencyService(FakeIdempotencyRepository())
    await service.claim(_attempt())

    assert (await service.claim(_attempt())).state is ClaimState.IN_FLIGHT


async def test_a_repeat_of_a_finished_call_replays_what_it_answered() -> None:
    service = IdempotencyService(FakeIdempotencyRepository())
    await service.claim(_attempt())
    await service.complete(USER_ID, KEY, CREATED)

    claim = await service.claim(_attempt())

    assert claim.state is ClaimState.REPLAY
    assert claim.stored == CREATED


async def test_the_same_key_with_another_body_is_refused() -> None:
    service = IdempotencyService(FakeIdempotencyRepository())
    await service.claim(_attempt())
    await service.complete(USER_ID, KEY, CREATED)

    claim = await service.claim(_attempt(body=b'{"title":"two"}'))

    assert claim.state is ClaimState.MISMATCH


async def test_the_same_key_on_another_route_is_refused() -> None:
    service = IdempotencyService(FakeIdempotencyRepository())
    await service.claim(_attempt())

    claim = await service.claim(_attempt(path="/api/v1/roles"))

    assert claim.state is ClaimState.MISMATCH


async def test_one_account_never_replays_what_another_account_stored() -> None:
    repo = FakeIdempotencyRepository()
    service = IdempotencyService(repo)
    await service.claim(_attempt())
    await service.complete(USER_ID, KEY, CREATED)

    claim = await service.claim(Attempt(8, KEY, "POST", "/api/v1/items", b"{}"))

    assert claim.state is ClaimState.FRESH


async def test_a_released_key_can_be_used_again() -> None:
    service = IdempotencyService(FakeIdempotencyRepository())
    await service.claim(_attempt())

    await service.release(USER_ID, KEY)

    assert (await service.claim(_attempt())).state is ClaimState.FRESH


async def test_releasing_a_key_nobody_claimed_does_nothing() -> None:
    repo = FakeIdempotencyRepository()

    await IdempotencyService(repo).release(USER_ID, "never-used")

    assert repo.released == []


async def test_completing_a_key_nobody_claimed_does_nothing() -> None:
    repo = FakeIdempotencyRepository()

    await IdempotencyService(repo).complete(USER_ID, "never-used", CREATED)

    assert await repo.get(USER_ID, "never-used") is None


async def test_pruning_drops_only_what_aged_out() -> None:
    now = datetime.now(UTC)
    old = IdempotencyKey(
        key="old", user_id=USER_ID, method="POST", path="/x", request_hash="a"
    )
    old.created_at = now - timedelta(days=2)
    fresh = IdempotencyKey(
        key="fresh", user_id=USER_ID, method="POST", path="/x", request_hash="b"
    )
    fresh.created_at = now
    repo = FakeIdempotencyRepository([old, fresh])

    dropped = await IdempotencyService(repo).prune_batch(timedelta(days=1), 100)

    assert dropped == 1
    assert await repo.get(USER_ID, "fresh") is not None


def test_the_fingerprint_covers_method_path_and_body() -> None:
    base = _attempt()

    assert fingerprint(base) == fingerprint(_attempt())
    assert fingerprint(base) != fingerprint(_attempt(body=b"{}"))
    assert fingerprint(base) != fingerprint(_attempt(path="/other"))
    assert fingerprint(base) != fingerprint(
        Attempt(USER_ID, KEY, "PATCH", "/api/v1/items", base.body)
    )


async def test_a_claim_nobody_finished_is_taken_over_once_it_is_stale() -> None:
    repo = FakeIdempotencyRepository()
    service = IdempotencyService(repo, in_flight_timeout=timedelta(seconds=30))
    await service.claim(_attempt())
    abandoned = await repo.get(USER_ID, KEY)
    assert abandoned is not None
    abandoned.created_at = datetime.now(UTC) - timedelta(minutes=5)

    assert (await service.claim(_attempt())).state is ClaimState.FRESH


async def test_a_claim_still_inside_its_window_is_left_alone() -> None:
    service = IdempotencyService(
        FakeIdempotencyRepository(), in_flight_timeout=timedelta(minutes=5)
    )
    await service.claim(_attempt())

    assert (await service.claim(_attempt())).state is ClaimState.IN_FLIGHT


async def test_taking_a_stale_claim_over_accepts_the_body_it_now_carries() -> None:
    repo = FakeIdempotencyRepository()
    service = IdempotencyService(repo, in_flight_timeout=timedelta(seconds=30))
    await service.claim(_attempt())
    abandoned = await repo.get(USER_ID, KEY)
    assert abandoned is not None
    abandoned.created_at = datetime.now(UTC) - timedelta(minutes=5)

    claim = await service.claim(_attempt(body=b'{"title":"two"}'))

    assert claim.state is ClaimState.FRESH


async def test_a_finished_claim_is_never_taken_over_however_old_it_is() -> None:
    repo = FakeIdempotencyRepository()
    service = IdempotencyService(repo, in_flight_timeout=timedelta(seconds=30))
    await service.claim(_attempt())
    await service.complete(USER_ID, KEY, CREATED)
    stored = await repo.get(USER_ID, KEY)
    assert stored is not None
    stored.created_at = datetime.now(UTC) - timedelta(days=1)

    assert (await service.claim(_attempt())).state is ClaimState.REPLAY
