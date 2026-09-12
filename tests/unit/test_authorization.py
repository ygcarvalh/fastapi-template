from app.core.authorization import ITEMS, READ, ROLES, DELETE, is_superuser, scope_for
from app.models.role import Scope
from app.models.user import User
from tests.unit.fakes import admin_role, role_with, user_role


def _user(role):
    return User(id=1, email="a@b.com", hashed_password="x", role=role)


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
