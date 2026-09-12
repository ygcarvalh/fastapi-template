import pytest

from app.core.audit.policy import AuditAction
from app.core.authorization import (
    BLOCKED_WHILE_IMPERSONATING,
    CREATE,
    DELETE,
    FEATURE_FLAGS,
    IMPERSONATE,
    READ,
    ROLES,
    UPDATE,
    USERS,
    may_impersonate,
)
from app.core.exceptions import ForbiddenError
from app.core.security import decode_access_token, hash_password
from app.models.role import Role, Scope
from app.models.user import User
from app.schemas.audit_log import AuditLogQuery
from app.services.auth_service import AuthService
from tests.unit.fakes import (
    FakeAuditLogRepository,
    FakeRefreshTokenRepository,
    FakeUserRepository,
    admin_role,
    role_with,
    user_role,
)

PASSWORD = "the-correct-password"


def _user(user_id: int, *roles: Role) -> User:
    account = User(
        email=f"user{user_id}@example.com", hashed_password=hash_password(PASSWORD)
    )
    account.id = user_id
    account.roles = list(roles)
    return account


def _support_role() -> Role:
    return role_with(
        "support", [(USERS, READ, Scope.ALL), (USERS, IMPERSONATE, Scope.ALL)]
    )


def _service(*accounts: User) -> tuple[AuthService, FakeAuditLogRepository]:
    audit = FakeAuditLogRepository()
    return (
        AuthService(FakeUserRepository(accounts), FakeRefreshTokenRepository(), audit),
        audit,
    )


def test_an_account_without_the_permission_impersonates_nobody() -> None:
    assert not may_impersonate(_user(1, user_role()), _user(2, user_role()))


def test_the_permission_is_what_opens_it_not_the_role_name() -> None:
    assert may_impersonate(_user(1, _support_role()), _user(2, user_role()))


def test_a_superadmin_is_out_of_reach_of_everyone_below() -> None:
    assert not may_impersonate(_user(1, _support_role()), _user(2, admin_role()))


def test_a_superadmin_reaches_another_superadmin() -> None:
    assert may_impersonate(_user(1, admin_role()), _user(2, admin_role()))


def test_the_writes_that_would_widen_reach_are_closed_for_the_duration() -> None:
    assert (ROLES, CREATE) in BLOCKED_WHILE_IMPERSONATING
    assert (ROLES, UPDATE) in BLOCKED_WHILE_IMPERSONATING
    assert (ROLES, DELETE) in BLOCKED_WHILE_IMPERSONATING
    assert (USERS, UPDATE) in BLOCKED_WHILE_IMPERSONATING
    assert (FEATURE_FLAGS, UPDATE) in BLOCKED_WHILE_IMPERSONATING


def test_impersonation_cannot_be_chained() -> None:
    assert (USERS, IMPERSONATE) in BLOCKED_WHILE_IMPERSONATING


def test_reading_is_never_closed_off_by_impersonating() -> None:
    assert (USERS, READ) not in BLOCKED_WHILE_IMPERSONATING
    assert (ROLES, READ) not in BLOCKED_WHILE_IMPERSONATING


async def test_a_grant_names_the_target_and_carries_no_refresh_token() -> None:
    actor, target = _user(1, admin_role()), _user(2, user_role())
    service, _audit = _service(actor, target)

    grant = await service.impersonate(actor, target)

    claims = decode_access_token(grant.access_token)
    assert claims.subject == "2"
    assert claims.impersonator == "1"
    assert grant.expires_in > 0


async def test_an_account_cannot_impersonate_itself() -> None:
    actor = _user(1, admin_role())
    service, _audit = _service(actor)

    with pytest.raises(ForbiddenError):
        await service.impersonate(actor, actor)


async def test_a_target_beyond_the_actors_reach_is_refused() -> None:
    actor, target = _user(1, _support_role()), _user(2, admin_role())
    service, _audit = _service(actor, target)

    with pytest.raises(ForbiddenError):
        await service.impersonate(actor, target)


async def test_starting_and_stopping_both_reach_the_trail() -> None:
    actor, target = _user(1, admin_role()), _user(2, user_role())
    service, audit = _service(actor, target)

    await service.impersonate(actor, target)
    await service.stop_impersonating(target)

    recorded = await audit.list_page(AuditLogQuery(limit=100))
    assert [entry.action for entry in recorded] == [
        AuditAction.IMPERSONATE_STOP,
        AuditAction.IMPERSONATE_START,
    ]
    assert {entry.row_pk for entry in recorded} == {"2"}
