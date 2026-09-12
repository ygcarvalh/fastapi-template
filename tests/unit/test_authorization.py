from app.core.authorization import (
    DELETE,
    ITEMS,
    READ,
    REQUEST_LOG,
    ROLES,
    granted,
    is_superuser,
    scope_for,
)
from app.models.role import Role, Scope
from app.models.user import User
from tests.unit.fakes import admin_role, role_with, user_role


def _user(*roles: Role) -> User:
    return User(id=1, email="a@b.com", hashed_password="x", roles=list(roles))


def test_an_administrator_reaches_everything_without_a_grant_row() -> None:
    stripped = role_with("superadmin", [])
    account = _user(stripped)

    assert is_superuser(account)
    assert scope_for(account, ITEMS, READ) == Scope.ALL
    assert scope_for(account, "anything-added-later", DELETE) == Scope.ALL


def test_an_administrator_keeps_reaching_everything_when_rows_say_otherwise() -> None:
    narrowed = role_with("superadmin", [(ITEMS, READ, Scope.OWN)])

    assert scope_for(_user(narrowed), ITEMS, READ) == Scope.ALL


def test_everyone_else_holds_only_what_was_granted() -> None:
    account = _user(user_role())

    assert not is_superuser(account)
    assert scope_for(account, ITEMS, READ) == Scope.OWN
    assert scope_for(account, ROLES, DELETE) is None


def test_the_seeded_administrator_is_a_superuser() -> None:
    assert is_superuser(_user(admin_role()))


def test_an_account_holding_no_role_reaches_nothing() -> None:
    account = _user()

    assert not is_superuser(account)
    assert scope_for(account, ITEMS, READ) is None
    assert granted(account) == []


def test_the_grants_of_every_role_add_up() -> None:
    account = _user(
        role_with("reader", [(ITEMS, READ, Scope.OWN)]),
        role_with("auditor", [(REQUEST_LOG, READ, Scope.ALL)]),
    )

    assert scope_for(account, ITEMS, READ) == Scope.OWN
    assert scope_for(account, REQUEST_LOG, READ) == Scope.ALL


def test_the_widest_scope_wins_when_two_roles_overlap() -> None:
    narrow = role_with("reader", [(ITEMS, READ, Scope.OWN)])
    wide = role_with("auditor", [(ITEMS, READ, Scope.ALL)])

    assert scope_for(_user(narrow, wide), ITEMS, READ) == Scope.ALL
    assert scope_for(_user(wide, narrow), ITEMS, READ) == Scope.ALL


def test_an_overlapping_permission_is_listed_once() -> None:
    account = _user(
        role_with("reader", [(ITEMS, READ, Scope.OWN)]),
        role_with("auditor", [(ITEMS, READ, Scope.ALL)]),
    )

    assert granted(account) == [(ITEMS, READ, Scope.ALL)]


def test_a_superadmin_role_alongside_another_still_rules() -> None:
    account = _user(user_role(), role_with("superadmin", []))

    assert is_superuser(account)
    assert scope_for(account, ROLES, DELETE) == Scope.ALL
