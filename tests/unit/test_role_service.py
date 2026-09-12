import pytest

from app.core.authorization import ITEMS, READ, USERS
from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.role import Scope
from app.schemas.role import GrantWrite, RoleWrite
from app.services.role_service import RoleService
from tests.unit.fakes import (
    FakePermissionRepository,
    FakeRoleRepository,
    FakeUserRepository,
)


def setup() -> tuple[RoleService, FakeRoleRepository, FakeUserRepository]:
    roles = FakeRoleRepository()
    users = FakeUserRepository()
    return RoleService(roles, FakePermissionRepository(), users), roles, users


async def test_a_new_role_carries_the_grants_it_was_given() -> None:
    service, _roles, _users = setup()

    created = await service.create(
        RoleWrite(
            name="finance",
            grants=[GrantWrite(resource=ITEMS, action=READ, scope=Scope.ALL)],
        )
    )

    assert created.name == "finance"
    assert [
        (g.permission.resource, g.permission.action, g.scope) for g in created.grants
    ] == [(ITEMS, READ, Scope.ALL)]


async def test_a_role_name_is_taken_only_once() -> None:
    service, _roles, _users = setup()

    with pytest.raises(ConflictError):
        await service.create(RoleWrite(name="admin", grants=[]))


async def test_a_grant_nobody_defined_is_refused() -> None:
    service, _roles, _users = setup()

    with pytest.raises(NotFoundError):
        await service.create(
            RoleWrite(
                name="ghost",
                grants=[GrantWrite(resource="ledgers", action=READ, scope=Scope.OWN)],
            )
        )


async def test_updating_a_role_replaces_its_grants() -> None:
    service, roles, _users = setup()
    role = await roles.get_by_name("user")
    assert role is not None

    updated = await service.update(
        role.id,
        RoleWrite(
            name="user",
            grants=[GrantWrite(resource=USERS, action=READ, scope=Scope.ALL)],
        ),
    )

    assert [(g.permission.resource, g.permission.action) for g in updated.grants] == [
        (USERS, READ)
    ]


async def test_a_role_the_deployment_ships_cannot_be_deleted() -> None:
    service, roles, _users = setup()
    role = await roles.get_by_name("admin")
    assert role is not None

    with pytest.raises(ForbiddenError):
        await service.delete(role.id)


async def test_a_role_that_still_has_accounts_cannot_be_deleted() -> None:
    service, _roles, users = setup()
    created = await service.create(RoleWrite(name="finance", grants=[]))
    users.role_counts[created.id] = 1

    with pytest.raises(ConflictError):
        await service.delete(created.id)


async def test_an_empty_role_is_deleted() -> None:
    service, roles, _users = setup()
    created = await service.create(RoleWrite(name="finance", grants=[]))

    await service.delete(created.id)

    assert [role.name for role in roles.deleted] == ["finance"]


async def test_reading_a_role_that_is_not_there_raises() -> None:
    service, _roles, _users = setup()

    with pytest.raises(NotFoundError):
        await service.get(404)
